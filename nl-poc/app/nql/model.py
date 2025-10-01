"""Typed models for NQL v0.1."""
from __future__ import annotations

from typing import List, Literal, Optional, get_args, get_origin

try:  # pragma: no cover - exercised in environments with Pydantic installed
    from pydantic import BaseModel, Field  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - fallback for lightweight test envs
    import copy as _copy
    from typing import get_type_hints

    class _FieldInfo:
        def __init__(self, default=None, default_factory=None):
            self.default = default
            self.default_factory = default_factory

    def Field(default=None, default_factory=None, **_kwargs):  # type: ignore
        if default_factory is not None:
            return _FieldInfo(default=None, default_factory=default_factory)
        return _FieldInfo(default=default)

    _UNSET = object()

    class BaseModel:  # type: ignore
        class Config:
            extra = "ignore"

        def __init__(self, **data):
            annotations = get_type_hints(self.__class__)
            setattr(self.__class__, "__nql_fields__", list(annotations.keys()))
            extras = {k: v for k, v in data.items() if k not in annotations}
            if extras and getattr(self.Config, "extra", "ignore") == "forbid":
                unknown = ", ".join(sorted(extras))
                raise ValueError(f"Unknown field(s): {unknown}")
            for name, annotation in annotations.items():
                if name in data:
                    raw_value = data[name]
                else:
                    attr = getattr(self.__class__, name, _UNSET)
                    if isinstance(attr, _FieldInfo):
                        if attr.default_factory is not None:
                            raw_value = attr.default_factory()
                        else:
                            raw_value = attr.default
                    elif attr is _UNSET:
                        raw_value = None
                    else:
                        raw_value = _copy.deepcopy(attr)
                value = self._convert(annotation, raw_value)
                setattr(self, name, value)

        @classmethod
        def _convert(cls, annotation, value):
            if value is None:
                return None
            origin = get_origin(annotation)
            if origin is Literal:
                choices = get_args(annotation)
                if value not in choices:
                    raise ValueError(f"Value '{value}' not permitted; expected one of {choices}")
                return value
            if origin in (list, List):
                (item_type,) = get_args(annotation)
                return [cls._convert(item_type, item) for item in value]
            if origin is Optional:
                (inner,) = get_args(annotation)
                return cls._convert(inner, value)
            if origin is not None and str(origin).endswith("Union"):
                args = [arg for arg in get_args(annotation) if arg is not type(None)]
                if not args:
                    return value
                return cls._convert(args[0], value)
            if isinstance(annotation, type) and issubclass(annotation, BaseModel):
                if isinstance(value, annotation):
                    return value
                if isinstance(value, dict):
                    return annotation.parse_obj(value)
            return value

        @classmethod
        def parse_obj(cls, obj):
            if isinstance(obj, cls):
                return obj
            if not isinstance(obj, dict):
                raise TypeError("parse_obj expects a dict payload")
            return cls(**obj)

        def copy(self, deep: bool = False):
            if deep:
                return _copy.deepcopy(self)
            return self.__class__(**self.dict())

        def dict(self):
            payload = {}
            field_names = getattr(self.__class__, "__nql_fields__", [])
            if not field_names:
                field_names = list(get_type_hints(self.__class__).keys())
            for name in field_names:
                value = getattr(self, name)
                if isinstance(value, BaseModel):
                    payload[name] = value.dict()
                elif isinstance(value, list):
                    items = []
                    for item in value:
                        if isinstance(item, BaseModel):
                            items.append(item.dict())
                        else:
                            items.append(item)
                    payload[name] = items
                else:
                    payload[name] = value
            return payload


IntentType = Literal["aggregate", "detail", "trend", "compare", "rank", "distribution"]
MetricAgg = Literal["count", "sum", "avg", "min", "max", "distinct_count"]
FilterOp = Literal["=", "!=", ">", ">=", "<", "<=", "between", "in", "not_in", "like", "like_any", "ilike", "regex"]
FilterType = Literal["text", "text_raw", "number", "date", "category"]
TimeGrain = Literal["day", "week", "month", "quarter", "year"]
WindowType = Literal["single_month", "absolute", "quarter", "relative_months", "ytd"]
CompareType = Literal["mom", "yoy", "wow", "dod"]
CompareBaseline = Literal["previous_period", "same_period_last_year"]
SortDirection = Literal["asc", "desc"]


class Metric(BaseModel):
    name: str
    agg: MetricAgg
    alias: str

    class Config:
        extra = "forbid"


class Filter(BaseModel):
    field: str
    op: FilterOp
    value: object
    type: FilterType
    notes: Optional[str] = None

    class Config:
        extra = "forbid"


class TimeWindow(BaseModel):
    type: WindowType
    start: Optional[str] = None
    end: Optional[str] = None
    exclusive_end: bool = False
    n: Optional[int] = Field(default=None, ge=1)

    class Config:
        extra = "forbid"


class TimeSpec(BaseModel):
    grain: TimeGrain
    window: TimeWindow
    tz: str = "America/Chicago"

    class Config:
        extra = "forbid"


class CompareInternalWindow(BaseModel):
    expand_prior: bool = False

    class Config:
        extra = "forbid"


class CompareSpec(BaseModel):
    type: CompareType
    baseline: Optional[CompareBaseline] = None
    internal_window: Optional[CompareInternalWindow] = None

    class Config:
        extra = "forbid"


class Flags(BaseModel):
    trend: Optional[bool] = None
    strict_json: bool = True
    require_grouping_for_trend: bool = True
    like_passthrough: bool = True
    single_month_equals: bool = True
    quarter_exclusive_end: bool = True
    rowcap_hint: int = 10_000

    class Config:
        extra = "forbid"


class Provenance(BaseModel):
    utterance: Optional[str] = None
    retrieval_notes: List[str] = Field(default_factory=list)
    confidence: Optional[float] = Field(default=None, ge=0, le=1)
    critic_pass: List[str] = Field(default_factory=list)

    class Config:
        extra = "forbid"


class SortSpec(BaseModel):
    by: str
    dir: SortDirection

    class Config:
        extra = "forbid"


class NQLQuery(BaseModel):
    nql_version: Literal["0.1"]
    intent: IntentType
    dataset: str
    metrics: List[Metric]
    time: TimeSpec
    dimensions: List[str] = Field(default_factory=list)
    filters: List[Filter] = Field(default_factory=list)
    compare: Optional[CompareSpec] = None
    group_by: List[str] = Field(default_factory=list)
    sort: List[SortSpec] = Field(default_factory=list)
    limit: int = Field(default=100, ge=1)
    flags: Flags = Field(default_factory=Flags)
    provenance: Provenance = Field(default_factory=Provenance)

    class Config:
        extra = "forbid"
