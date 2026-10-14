"""Versioned content contracts. Facts and conditional analysis carry explicit evidence."""

from datetime import date
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Key = str


class ContentModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Evidence(ContentModel):
    source_id: str
    locator: str = Field(min_length=2)
    summary: str = Field(min_length=4)


class Source(ContentModel):
    category: Literal["primary", "vendor", "framework"] = "primary"
    snapshot_hash: str | None = None
    id: str = Field(pattern=r"^[a-z0-9_-]+$")
    title: str
    url: str
    published_on: date | None = None
    retrieved_on: date
    report_period: str | None = None
    access_status: Literal["verified", "search_verified", "unavailable"] = "verified"

    @field_validator("url")
    @classmethod
    def safe_url(cls, value):
        u = urlsplit(value)
        if u.scheme not in ("https", "http") or not u.hostname or u.username or u.password:
            raise ValueError("资料必须使用有效 HTTP(S) 链接")
        return value


class Analysis(ContentModel):
    id: str
    trigger: str
    target: str
    direction: Literal["有利", "不利", "混合", "不确定"]
    mechanism: str
    conditions: str = Field(min_length=4)
    horizon: str
    indicators: list[str] = Field(min_length=1)
    kind: Literal["事实", "分析判断"] = "分析判断"
    evidence: list[Evidence] = Field(min_length=1)


class Node(ContentModel):
    assertion_kind: Literal["事实", "分析框架"] = "事实"
    key: str = Field(pattern=r"^[a-z0-9_-]+$")
    name: str
    stage: Literal["资源", "材料", "设计", "制造", "应用", "设备", "服务", "回收"]
    description: str
    variable: str
    main: bool = True
    column: int = Field(ge=0, le=12)
    order: int = Field(default=0, ge=0)
    competition: str = "暂无同口径竞争格局数据，不提供综合排名。"
    gap: str = ""
    evidence: list[Evidence] = Field(min_length=1)
    analyses: list[Analysis] = []


class Edge(ContentModel):
    assertion_kind: Literal["事实", "分析判断"] = "事实"
    key: str = Field(pattern=r"^[a-z0-9_-]+$")
    source: str
    target: str
    kind: Literal["供给", "需求反馈", "技术替代", "循环"] = "供给"
    description: str
    conditions: str
    evidence: list[Evidence] = Field(min_length=1)


class Metric(ContentModel):
    verification: Literal["原始资料核验", "数据商汇总待核验"] = "原始资料核验"
    period: str = Field(pattern=r"^\d{4}-(?:FY|H1|Q[1-4])$")
    disclosed_on: date | None = None
    subject: str
    basis: str
    currency: Literal["CNY", "USD", "HKD"] = "CNY"
    revenue: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    share: float | None = Field(default=None, ge=0, le=100, allow_inf_nan=False)
    denominator: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    missing_reason: str = "未取得可核验的同口径分部收入。"
    evidence: list[Evidence] = Field(min_length=1)

    @model_validator(mode="after")
    def check_share(self):
        if self.share is not None:
            if self.revenue is None or self.denominator is None or not self.basis.strip():
                raise ValueError("收入占比需要同口径收入、分母与口径")
            if abs(self.share - 100 * self.revenue / self.denominator) > 0.05:
                raise ValueError("收入占比与分子分母不符")
        return self


class Leader(ContentModel):
    kind: Literal["规模龙头", "份额龙头", "技术领先企业", "代表企业"]
    product: str
    geography: str
    period: str
    reason: str
    evidence: list[Evidence] = Field(min_length=1)


class StockLink(ContentModel):
    company_analysis: list[str] = []
    mapping_status: Literal["资料核验", "业务词匹配", "分类候选"] = "资料核验"
    financial_status: str = "未采集"
    key: str = Field(pattern=r"^[a-z0-9_-]+$")
    node: str
    ts_code: str = Field(pattern=r"^\d{6}\.(SH|SZ|BJ)$")
    subject: str
    business: str
    participation: Literal["直接经营", "控股子公司", "参股", "其他已披露方式", "待核实"]
    operating_stage: Literal["已形成收入", "已开展经营", "试产", "建设中", "研发中", "未知"]
    evidence: list[Evidence] = Field(min_length=1)
    metrics: list[Metric] = []
    leaders: list[Leader] = []


class ChainDocument(ContentModel):
    schema_version: Literal[1] = 1
    coverage_level: Literal["curated", "baseline"] = "curated"
    business_model: str = "production"
    analysis_version: int = Field(default=1, ge=1, le=2)
    industry_level: int | None = None
    parent_industry_id: str | None = None
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,63}$")
    name: str
    aliases: list[str] = []
    industry_ids: list[str] = []
    scope: str
    summary: str
    demand: str
    focus: list[str]
    content_as_of: date
    change_note: str
    sources: list[Source] = Field(min_length=1)
    nodes: list[Node] = Field(min_length=1, max_length=150)
    edges: list[Edge] = Field(max_length=600)
    stocks: list[StockLink] = []
    gaps: list[str] = []

    @model_validator(mode="after")
    def references(self):
        def unique(items, field):
            keys = [getattr(x, field) for x in items]
            if len(set(keys)) != len(keys):
                raise ValueError(f"重复身份：{field}")
            return set(keys)

        sources = unique(self.sources, "id")
        nodes = unique(self.nodes, "key")
        unique(self.edges, "key")
        unique(self.stocks, "key")
        for e in self.edges:
            if e.source not in nodes or e.target not in nodes or e.source == e.target:
                raise ValueError("连线端点不存在或自连")
        for link in self.stocks:
            if link.node not in nodes:
                raise ValueError("股票节点不存在")
        for s in self.sources:
            if s.retrieved_on > self.content_as_of:
                raise ValueError("资料取得日晚于资料截至日")
            if s.published_on and s.published_on > s.retrieved_on:
                raise ValueError("披露日晚于取得日")

        def walk(value):
            if isinstance(value, BaseModel):
                for k in type(value).model_fields:
                    walk(getattr(value, k))
            elif isinstance(value, list):
                for x in value:
                    walk(x)
            if isinstance(value, Evidence) and value.source_id not in sources:
                raise ValueError("引用的资料来源不存在")

        walk(self)
        return self
