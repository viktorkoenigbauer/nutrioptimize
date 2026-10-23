"""Read-only adapter for YAZIO's undocumented private API.

YAZIO does not publish or support this interface.  Keep the HTTP boundary in
this one module so an upstream change cannot leak through the rest of the
application.  The adapter deliberately implements only the reads needed for
the nutrition diary; it never writes to the YAZIO account.
"""

import asyncio
import hashlib
import json
import logging
from collections.abc import Awaitable, Callable, Hashable, Iterable, Mapping
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, TypeVar
from urllib.parse import quote
from zoneinfo import ZoneInfo

import httpx

from app.domain import (
    NUTRIENT_UNITS,
    NormalizedDailyGoal,
    NormalizedFoodEntry,
    Nutrient,
    canonical_payload_hash,
)

logger = logging.getLogger(__name__)


class YazioError(RuntimeError):
    """Base class whose message is safe to store in local diagnostics."""


class YazioAuthenticationError(YazioError):
    pass


class YazioClientVersionBlocked(YazioError):
    pass


class YazioUpstreamError(YazioError):
    pass


class YazioProtocolError(YazioError):
    pass


# YAZIO returns energy in kcal and every other nutrient in grams per base unit.
# The factor converts grams to the unit used by NutriOptimize.  The keys and
# scaling rules are derived from the community API specification and verified
# exporter linked in docs/YAZIO_UNOFFICIAL_API.md.
YAZIO_NUTRIENTS: dict[str, tuple[str, Decimal]] = {
    "energy.energy": ("energy_kcal", Decimal("1")),
    "nutrient.carb": ("carbohydrate_g", Decimal("1")),
    "nutrient.protein": ("protein_g", Decimal("1")),
    "nutrient.fat": ("fat_g", Decimal("1")),
    "nutrient.saturated": ("saturated_fat_g", Decimal("1")),
    "nutrient.monounsaturated": ("monounsaturated_fat_g", Decimal("1")),
    "nutrient.polyunsaturated": ("polyunsaturated_fat_g", Decimal("1")),
    "nutrient.transfat": ("trans_fat_g", Decimal("1")),
    "nutrient.cholesterol": ("cholesterol_mg", Decimal("1000")),
    "nutrient.dietaryfiber": ("fiber_g", Decimal("1")),
    "nutrient.sugar": ("sugar_g", Decimal("1")),
    "nutrient.addedsugar": ("added_sugar_g", Decimal("1")),
    "nutrient.salt": ("salt_g", Decimal("1")),
    "nutrient.sodium": ("sodium_mg", Decimal("1000")),
    "nutrient.water": ("water_g", Decimal("1")),
    "nutrient.alcohol": ("alcohol_g", Decimal("1")),
    "vitamin.a": ("vitamin_a_ug", Decimal("1000000")),
    "vitamin.b1": ("vitamin_b1_mg", Decimal("1000")),
    "vitamin.b2": ("vitamin_b2_mg", Decimal("1000")),
    "vitamin.b3": ("vitamin_b3_mg", Decimal("1000")),
    "vitamin.b5": ("vitamin_b5_mg", Decimal("1000")),
    "vitamin.b6": ("vitamin_b6_mg", Decimal("1000")),
    "vitamin.b7": ("vitamin_b7_ug", Decimal("1000000")),
    "vitamin.b11": ("folate_ug", Decimal("1000000")),
    "vitamin.b12": ("vitamin_b12_ug", Decimal("1000000")),
    "vitamin.c": ("vitamin_c_mg", Decimal("1000")),
    "vitamin.d": ("vitamin_d_ug", Decimal("1000000")),
    "vitamin.e": ("vitamin_e_mg", Decimal("1000")),
    "vitamin.k": ("vitamin_k_ug", Decimal("1000000")),
    "mineral.calcium": ("calcium_mg", Decimal("1000")),
    "mineral.iron": ("iron_mg", Decimal("1000")),
    "mineral.magnesium": ("magnesium_mg", Decimal("1000")),
    "mineral.phosphorus": ("phosphorus_mg", Decimal("1000")),
    "mineral.potassium": ("potassium_mg", Decimal("1000")),
    "mineral.zinc": ("zinc_mg", Decimal("1000")),
    "mineral.copper": ("copper_mg", Decimal("1000")),
    "mineral.manganese": ("manganese_mg", Decimal("1000")),
    "mineral.selenium": ("selenium_ug", Decimal("1000000")),
    "mineral.iodine": ("iodine_ug", Decimal("1000000")),
    "mineral.chlorine": ("chloride_mg", Decimal("1000")),
    "mineral.sulfur": ("sulfur_mg", Decimal("1000")),
    "mineral.fluoride": ("fluoride_mg", Decimal("1000")),
    "mineral.fluorine": ("fluorine_mg", Decimal("1000")),
    "mineral.biotin": ("biotin_ug", Decimal("1000000")),
    "mineral.choline": ("choline_mg", Decimal("1000")),
    "mineral.chrome": ("chromium_ug", Decimal("1000000")),
    "mineral.cobalt": ("cobalt_ug", Decimal("1000000")),
    "mineral.molybdenum": ("molybdenum_ug", Decimal("1000000")),
    "mineral.boron": ("boron_mg", Decimal("1000")),
    "mineral.silicon": ("silicon_mg", Decimal("1000")),
    "mineral.arsenic": ("arsenic_ug", Decimal("1000000")),
    "mineral.rubidium": ("rubidium_ug", Decimal("1000000")),
    "mineral.tin": ("tin_mg", Decimal("1000")),
    "mineral.vanadium": ("vanadium_ug", Decimal("1000000")),
}

# Daily goal responses use human units already, unlike product nutrients.  The
# short aliases have appeared in older captures, so accepting them keeps this
# read path tolerant without weakening validation of the values themselves.
YAZIO_GOALS: dict[str, tuple[str, str]] = {
    "energy.energy": ("energy_kcal", "kcal"),
    "energy": ("energy_kcal", "kcal"),
    "nutrient.protein": ("protein_g", "g"),
    "protein": ("protein_g", "g"),
    "nutrient.fat": ("fat_g", "g"),
    "fat": ("fat_g", "g"),
    "nutrient.carb": ("carbohydrate_g", "g"),
    "carb": ("carbohydrate_g", "g"),
}

Key = TypeVar("Key", bound=Hashable)
Value = TypeVar("Value")


def _inclusive_dates(start_date: date, end_date: date) -> list[date]:
    """Return each calendar day in a validated inclusive range."""
    if start_date > end_date:
        raise ValueError("start_date must be before or equal to end_date")
    day_count = (end_date - start_date).days + 1
    return [start_date + timedelta(days=offset) for offset in range(day_count)]


class YazioSource:
    name = "yazio"
    authoritative_window = True

    def __init__(
        self,
        *,
        timezone_name: str,
        email: str,
        password: str,
        client_id: str,
        client_secret: str,
        base_url: str = "https://yzapi.yazio.com",
        api_version: str = "v22",
        user_agent: str,
        accept_language: str = "de-AT,de;q=0.9,en;q=0.8",
        timeout_seconds: float = 20.0,
        max_concurrency: int = 4,
        http_client: httpx.AsyncClient | None = None,
    ):
        self.timezone_name = timezone_name
        self.timezone = ZoneInfo(timezone_name)
        self.email = email
        self.password = password
        self.client_id = client_id
        self.client_secret = client_secret
        self.api_version = api_version.strip("/")
        self.user_agent = user_agent
        self.accept_language = accept_language
        self.max_concurrency = max_concurrency
        self._access_token: str | None = None
        self._refresh_token: str | None = None
        self._owns_client = http_client is None
        self._client = http_client or httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=httpx.Timeout(timeout_seconds),
        )
        self._unknown_nutrients: set[str] = set()

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def fetch_entries(
        self, start_date: date, end_date: date
    ) -> list[NormalizedFoodEntry]:
        self._unknown_nutrients.clear()
        days = _inclusive_dates(start_date, end_date)

        day_payloads = await self._bounded_map(days, self._fetch_day)
        product_ids = {
            str(item["product_id"])
            for payload in day_payloads.values()
            for item in self._list(payload, "products")
            if item.get("product_id")
        }
        recipe_ids = {
            str(item["recipe_id"])
            for payload in day_payloads.values()
            for item in self._list(payload, "recipe_portions")
            if item.get("recipe_id")
        }

        products = await self._bounded_map(product_ids, self._fetch_product)
        recipes = await self._bounded_map(recipe_ids, self._fetch_recipe)

        entries: list[NormalizedFoodEntry] = []
        for day in days:
            payload = day_payloads[day]
            entries.extend(self._normalize_products(payload, products))
            entries.extend(self._normalize_recipes(payload, recipes))
            entries.extend(self._normalize_simple_products(payload))

        if self._unknown_nutrients:
            # Nutrient identifiers are schema metadata, not diary content.  We
            # report them so a new upstream field is never silently mistaken
            # for a tracked zero.
            logger.warning(
                "YAZIO returned unsupported nutrient keys: %s",
                ", ".join(sorted(self._unknown_nutrients)),
            )
        return entries

    async def fetch_daily_goals(
        self, start_date: date, end_date: date
    ) -> list[NormalizedDailyGoal]:
        days = _inclusive_dates(start_date, end_date)
        return list((await self._bounded_map(days, self._fetch_daily_goal)).values())

    async def _bounded_map(
        self, keys: Iterable[Key], fetch: Callable[[Key], Awaitable[Value]]
    ) -> dict[Key, Value]:
        semaphore = asyncio.Semaphore(self.max_concurrency)

        async def one(key: Key) -> tuple[Key, Value]:
            async with semaphore:
                return key, await fetch(key)

        return dict(await asyncio.gather(*(one(key) for key in keys)))

    async def _fetch_day(self, day: date) -> dict[str, Any]:
        data = await self._get_json(
            f"/{self.api_version}/user/consumed-items",
            params={"date": day.isoformat()},
            allow_not_found=True,
        )
        if data is None:
            return {"products": [], "recipe_portions": [], "simple_products": []}
        if not isinstance(data, dict):
            raise YazioProtocolError("YAZIO diary response is not an object")
        return data

    async def _fetch_daily_goal(self, day: date) -> NormalizedDailyGoal:
        params = {"date": day.isoformat()}
        summary = await self._get_json(
            f"/{self.api_version}/user/widgets/daily-summary",
            params=params,
            allow_not_found=True,
        )
        if summary is not None and not isinstance(summary, Mapping):
            raise YazioProtocolError("YAZIO daily summary is not an object")

        effective_payload = summary.get("goals") if summary is not None else None
        if not isinstance(effective_payload, Mapping):
            effective_payload = await self._get_json(
                f"/{self.api_version}/user/goals", params=params
            )
        unmodified_payload = await self._get_json(
            f"/{self.api_version}/user/goals/unmodified", params=params
        )

        effective = self._goal_nutrients(effective_payload, "effective goals")
        unmodified = self._goal_nutrients(unmodified_payload, "unmodified goals")

        activity_energy = None
        consume_activity_energy = None
        if summary is not None:
            raw_activity = summary.get("activity_energy")
            if raw_activity is not None:
                activity_energy = self._decimal(raw_activity, "daily activity energy")
                if activity_energy < 0:
                    raise YazioProtocolError(
                        "YAZIO returned negative daily activity energy"
                    )
            raw_consume = summary.get("consume_activity_energy")
            if raw_consume is not None:
                if not isinstance(raw_consume, bool):
                    raise YazioProtocolError(
                        "YAZIO activity-energy preference is not boolean"
                    )
                consume_activity_energy = raw_consume

        # Persist only normalized goal fields and activity metadata.  The
        # summary response also contains profile information that is unrelated
        # to this feature and should not be copied into PostgreSQL.
        raw_payload = {
            "effective": {item.code: str(item.amount) for item in effective},
            "unmodified": {item.code: str(item.amount) for item in unmodified},
            "activity_energy_kcal": (
                str(activity_energy) if activity_energy is not None else None
            ),
            "consume_activity_energy": consume_activity_energy,
        }
        return NormalizedDailyGoal(
            source=self.name,
            local_date=day,
            timezone=self.timezone_name,
            effective=effective,
            unmodified=unmodified,
            activity_energy_kcal=activity_energy,
            consume_activity_energy=consume_activity_energy,
            raw_payload=raw_payload,
            payload_hash=canonical_payload_hash(raw_payload),
        )

    async def _fetch_product(self, product_id: str) -> dict[str, Any]:
        data = await self._get_json(
            f"/{self.api_version}/products/{quote(product_id, safe='')}"
        )
        if not isinstance(data, dict):
            raise YazioProtocolError("YAZIO product response is not an object")
        return data

    async def _fetch_recipe(self, recipe_id: str) -> dict[str, Any]:
        escaped = quote(recipe_id, safe="")
        data = await self._get_json(
            f"/{self.api_version}/recipes/{escaped}", allow_not_found=True
        )
        if data is None:
            data = await self._get_json(f"/{self.api_version}/user/recipes/{escaped}")
        if not isinstance(data, dict):
            raise YazioProtocolError("YAZIO recipe response is not an object")
        return data

    async def _get_json(
        self,
        path: str,
        *,
        params: Mapping[str, str] | None = None,
        allow_not_found: bool = False,
    ) -> Any:
        await self._ensure_authenticated()
        for attempt in range(2):
            response = await self._client.get(
                path,
                params=params,
                headers={
                    "Authorization": f"Bearer {self._access_token}",
                    "User-Agent": self.user_agent,
                    "Accept-Language": self.accept_language,
                    "Accept": "application/json",
                },
            )
            if response.status_code == 401 and attempt == 0:
                await self._refresh_or_login()
                continue
            if response.status_code == 404 and allow_not_found:
                return None
            if response.status_code == 403:
                raise YazioClientVersionBlocked(
                    "YAZIO rejected the configured API client version"
                )
            if response.status_code == 401:
                raise YazioAuthenticationError("YAZIO authentication was rejected")
            if not response.is_success:
                raise YazioUpstreamError(
                    f"YAZIO read failed with HTTP {response.status_code}"
                )
            try:
                return response.json()
            except ValueError as error:
                raise YazioProtocolError("YAZIO returned invalid JSON") from error
        raise YazioAuthenticationError("YAZIO authentication was rejected")

    async def _ensure_authenticated(self) -> None:
        if self._access_token is None:
            await self._login()

    async def _login(self) -> None:
        await self._request_token(
            {
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "username": self.email,
                "password": self.password,
                "grant_type": "password",
            }
        )

    async def _refresh_or_login(self) -> None:
        if self._refresh_token:
            try:
                await self._request_token(
                    {
                        "client_id": self.client_id,
                        "client_secret": self.client_secret,
                        "refresh_token": self._refresh_token,
                        "grant_type": "refresh_token",
                    }
                )
                return
            except YazioAuthenticationError:
                pass
        await self._login()

    async def _request_token(self, body: Mapping[str, str]) -> None:
        response = await self._client.post(
            f"/{self.api_version}/oauth/token",
            json=dict(body),
            headers={"User-Agent": self.user_agent, "Accept": "application/json"},
        )
        if response.status_code in (400, 401):
            raise YazioAuthenticationError("YAZIO credentials were rejected")
        if not response.is_success:
            raise YazioUpstreamError(
                f"YAZIO token exchange failed with HTTP {response.status_code}"
            )
        try:
            data = response.json()
        except ValueError as error:
            raise YazioProtocolError("YAZIO token response is invalid JSON") from error
        access_token = data.get("access_token") if isinstance(data, dict) else None
        if not isinstance(access_token, str) or not access_token:
            raise YazioProtocolError("YAZIO token response has no access token")
        self._access_token = access_token
        refresh_token = data.get("refresh_token")
        if isinstance(refresh_token, str) and refresh_token:
            self._refresh_token = refresh_token

    def _normalize_products(
        self, payload: Mapping[str, Any], products: Mapping[str, Mapping[str, Any]]
    ) -> list[NormalizedFoodEntry]:
        entries = []
        for item in self._list(payload, "products"):
            product_id = self._required_string(item, "product_id")
            product = products.get(product_id)
            if product is None:
                raise YazioProtocolError("YAZIO product details are missing")
            amount = self._decimal(item.get("amount"), "product amount")
            raw = {"kind": "product", "entry": item, "product": product}
            entries.append(
                self._entry(
                    kind="product",
                    item=item,
                    food_name=str(product.get("name") or f"Product {product_id}"),
                    quantity=amount,
                    unit=self._optional_string(product.get("base_unit")),
                    nutrients=self._nutrients(product.get("nutrients"), amount),
                    raw_payload=raw,
                )
            )
        return entries

    def _normalize_recipes(
        self, payload: Mapping[str, Any], recipes: Mapping[str, Mapping[str, Any]]
    ) -> list[NormalizedFoodEntry]:
        entries = []
        for item in self._list(payload, "recipe_portions"):
            recipe_id = self._required_string(item, "recipe_id")
            recipe = recipes.get(recipe_id)
            if recipe is None:
                raise YazioProtocolError("YAZIO recipe details are missing")
            portions = self._decimal(item.get("portion_count"), "recipe portions")
            raw = {"kind": "recipe_portion", "entry": item, "recipe": recipe}
            entries.append(
                self._entry(
                    kind="recipe",
                    item=item,
                    food_name=str(recipe.get("name") or f"Recipe {recipe_id}"),
                    quantity=portions,
                    unit="portion",
                    nutrients=self._nutrients(recipe.get("nutrients"), portions),
                    raw_payload=raw,
                )
            )
        return entries

    def _normalize_simple_products(
        self, payload: Mapping[str, Any]
    ) -> list[NormalizedFoodEntry]:
        entries = []
        for item in self._list(payload, "simple_products"):
            raw = {"kind": "simple_product", "entry": item}
            entries.append(
                self._entry(
                    kind="simple",
                    item=item,
                    food_name=str(item.get("name") or "Quick added"),
                    quantity=None,
                    unit=None,
                    nutrients=self._nutrients(item.get("nutrients"), Decimal("1")),
                    raw_payload=raw,
                )
            )
        return entries

    def _entry(
        self,
        *,
        kind: str,
        item: Mapping[str, Any],
        food_name: str,
        quantity: Decimal | None,
        unit: str | None,
        nutrients: list[Nutrient],
        raw_payload: Mapping[str, Any],
    ) -> NormalizedFoodEntry:
        consumed_at = self._local_datetime(item.get("date"))
        upstream_id = self._optional_string(item.get("id"))
        if upstream_id:
            external_id = f"{kind}:{upstream_id}"
        else:
            encoded = json.dumps(
                raw_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
            ).encode("utf-8")
            external_id = f"{kind}:derived:{hashlib.sha256(encoded).hexdigest()}"

        return NormalizedFoodEntry(
            source=self.name,
            external_id=external_id,
            consumed_at=consumed_at,
            local_date=consumed_at.astimezone(self.timezone).date(),
            timezone=self.timezone_name,
            meal=str(item.get("daytime") or "unknown"),
            food_name=food_name,
            quantity=quantity,
            unit=unit,
            nutrients=nutrients,
            raw_payload=raw_payload,
            payload_hash=canonical_payload_hash(raw_payload),
        )

    def _nutrients(self, raw: Any, scale: Decimal) -> list[Nutrient]:
        if raw is None:
            return []
        if not isinstance(raw, Mapping):
            raise YazioProtocolError("YAZIO nutrients are not an object")

        nutrients = []
        for upstream_code, raw_amount in raw.items():
            mapping = YAZIO_NUTRIENTS.get(str(upstream_code))
            if mapping is None:
                self._unknown_nutrients.add(str(upstream_code))
                continue
            code, factor = mapping
            amount = self._decimal(raw_amount, f"nutrient {upstream_code}")
            converted = amount * scale * factor
            if converted < 0:
                raise YazioProtocolError("YAZIO returned a negative nutrient amount")
            nutrients.append(
                Nutrient(code=code, amount=converted, unit=NUTRIENT_UNITS[code])
            )
        return nutrients

    def _goal_nutrients(self, raw: Any, label: str) -> list[Nutrient]:
        if not isinstance(raw, Mapping):
            raise YazioProtocolError(f"YAZIO {label} are not an object")
        if isinstance(raw.get("data"), Mapping):
            raw = raw["data"]

        nutrients = []
        seen_codes = set()
        for upstream_code, (code, unit) in YAZIO_GOALS.items():
            if upstream_code not in raw or code in seen_codes:
                continue
            amount = self._decimal(raw[upstream_code], f"{label} {upstream_code}")
            if amount < 0:
                raise YazioProtocolError(f"YAZIO returned negative {label}")
            nutrients.append(Nutrient(code=code, amount=amount, unit=unit))
            seen_codes.add(code)
        if "energy_kcal" not in seen_codes:
            raise YazioProtocolError(f"YAZIO {label} have no energy target")
        return nutrients

    def _local_datetime(self, raw: Any) -> datetime:
        if not isinstance(raw, str) or not raw.strip():
            raise YazioProtocolError("YAZIO diary entry has no timestamp")
        try:
            parsed = datetime.fromisoformat(raw.strip().replace(" ", "T"))
        except ValueError as error:
            raise YazioProtocolError("YAZIO diary timestamp is invalid") from error
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=self.timezone)
        return parsed.astimezone(self.timezone)

    @staticmethod
    def _list(payload: Mapping[str, Any], key: str) -> list[dict[str, Any]]:
        value = payload.get(key, [])
        if value is None:
            return []
        if not isinstance(value, list) or not all(
            isinstance(item, dict) for item in value
        ):
            raise YazioProtocolError(f"YAZIO field {key} is not a list of objects")
        return value

    @staticmethod
    def _required_string(payload: Mapping[str, Any], key: str) -> str:
        value = payload.get(key)
        if not isinstance(value, str) or not value:
            raise YazioProtocolError(f"YAZIO field {key} is missing")
        return value

    @staticmethod
    def _optional_string(value: Any) -> str | None:
        return value if isinstance(value, str) and value else None

    @staticmethod
    def _decimal(value: Any, label: str) -> Decimal:
        try:
            parsed = Decimal(str(value))
        except (InvalidOperation, ValueError) as error:
            raise YazioProtocolError(f"YAZIO {label} is not numeric") from error
        if not parsed.is_finite():
            raise YazioProtocolError(f"YAZIO {label} is not finite")
        return parsed
