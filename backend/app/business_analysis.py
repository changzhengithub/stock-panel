"""Industry-specific, conditional operating analysis; evidence and certainty stay separate."""

import csv
from functools import lru_cache

from app.settings import ROOT


@lru_cache(maxsize=1)
def analysis_rules():
    root = ROOT / "config/industry_models"
    return {
        filename: {
            row["行业"]: row
            for row in csv.DictReader((root / (filename + ".tsv")).open(), delimiter="\t")
        }
        for filename in ("business_logic", "sector_analysis")
    }


def assert_rule_coverage(specs):
    rules = analysis_rules()
    for specification, filename in (
        ("sectors", "sector_analysis"),
        ("subindustries", "business_logic"),
    ):
        expected = set(specs[specification])
        actual = set(rules[filename])
        if actual != expected:
            raise ValueError(
                f"{filename}业务分析未覆盖全部行业：缺少{sorted(expected - actual)}，额外{sorted(actual - expected)}"
            )
        for row in rules[filename].values():
            if any(not value.strip() for value in row.values()):
                raise ValueError("行业分析配置存在空白字段")


def enrich_operating_analysis(doc, industry, industries):
    rules = analysis_rules()
    parent = industries[industry.parent_id] if industry.parent_id else industry
    sector = rules["sector_analysis"][parent.name]
    children = {x.name: x for x in industries.values() if x.parent_id == industry.id}
    for node in doc["nodes"]:
        if node["key"] == "unassigned":
            continue
        business = (
            rules["business_logic"].get(node["name"])
            if industry.level == 1 and node["name"] in children
            else rules["business_logic"].get(industry.name)
        )
        logic = (
            business["经营逻辑"]
            if business
            else f"{parent.name}需要分别分析各业务分支。" + sector["需求传导"]
        )
        boundary = (
            business["适用边界"]
            if business
            else "一级行业分支并行经营，不能把不同产品和商业模式混为同一市场。"
        )
        name = node["name"]
        role = node["column"]
        refs = node["evidence"]
        if role == 1:
            node["description"] = f"{name}属于当前分析的核心经营活动。" + logic
            trigger = f"{name}的业务量、定价与产品结构变化"
            mechanism = logic
            cash_trigger = f"{name}的投入、结算与现金回收变化"
            cash_conditions = boundary
        elif role == 0:
            node["description"] = (
                f"{name}为{industry.name}提供投入或支持，其作用需要按实际产品与合同核对。"
                + sector["投入传导"]
            )
            trigger = f"{name}的价格、供给或技术适配变化"
            mechanism = f"当{name}实际进入相关业务时，" + sector["投入传导"]
            cash_trigger = f"{name}的采购、验证与资金占用变化"
            cash_conditions = "验证实际采购范围、交付及付款条款；" + boundary
        else:
            node["description"] = (
                f"{name}形成{industry.name}的应用或需求场景。" + sector["需求传导"]
            )
            trigger = f"{name}的使用、采购或投资需求变化"
            mechanism = sector["需求传导"] + " 对应核心经营活动：" + logic
            cash_trigger = f"{name}的交付、收费与回款变化"
            cash_conditions = "需区分需求意愿、已签合同和实际确认收入；" + boundary
        node["competition"] = (
            f"{name}的竞争地位应观察：{sector['竞争维度']}。产品、地域、期间与来源一致时才可比较；具体龙头认定仍需公司证据。"
        )
        node["analyses"] = [
            dict(
                id="operating",
                trigger=trigger,
                target=industry.name,
                direction="混合",
                mechanism=mechanism,
                conditions=boundary + " 需以该节点真实产品、客户或合同验证，未确认公司间交易。",
                horizon="按实际生产、服务交付或合同周期验证；量价与确认时点可能不同。",
                indicators=[node["variable"], *sector["竞争维度"].split("、")],
                kind="分析判断",
                evidence=refs,
            ),
            dict(
                id="cash-and-risk",
                trigger=cash_trigger,
                target=industry.name,
                direction="混合",
                mechanism=sector["现金流关注"],
                conditions=cash_conditions,
                horizon="重点观察最近报告期的应收、存货、合同负债或金融资本指标；不由收入直接推定现金。",
                indicators=sector["现金流关注"].rstrip("。").split("、"),
                kind="分析判断",
                evidence=refs,
            ),
        ]
    bykey = {n["key"]: n for n in doc["nodes"]}
    for edge in doc["edges"]:
        a = bykey[edge["source"]]
        b = bykey[edge["target"]]
        input_edge = a["column"] == 0 or b["column"] == 0
        specific = sector["投入传导"] if input_edge else sector["需求传导"]
        core = a if a["column"] == 1 else b
        core_rule = (
            rules["business_logic"].get(core["name"])
            if industry.level == 1
            else rules["business_logic"].get(industry.name)
        )
        boundary = core_rule["适用边界"] if core_rule else "需按各核心分支的真实业务验证。"
        if edge["kind"] == "供给":
            edge["description"] = f"{a['name']} → {b['name']}：" + specific
        else:
            edge["description"] = f"{a['name']}的需求反馈到{b['name']}：" + sector["需求传导"]
        edge["conditions"] = boundary + " 属于行业层面的条件路径，不确认这些候选公司间存在交易。"
    if industry.level == 2:
        doc["summary"] = rules["business_logic"][industry.name]["经营逻辑"]
    else:
        doc["summary"] = (
            f"{industry.name}覆盖"
            + "、".join(children)
            + "等分支。"
            + sector["投入传导"]
            + sector["需求传导"]
        )
    doc["analysis_version"] = 2
    doc["change_note"] = (
        "全行业专属经营分析：统一覆盖31个一级和134个二级行业，分别解释经营、投入、需求、现金流及竞争维度。公开业务与财务来源的核验状态单独标注。"
    )
    return doc


def explain_company(link, matched_terms):
    explanation = []
    if link.get("mapping_status") == "分类候选":
        explanation.append(
            "当前根据证券行业分类列为研究候选；主营资料尚不足以确认具体节点，不能将分类归属当作业务事实。"
        )
    elif matched_terms:
        explanation.append(
            "主营业务文字或产品分部命中："
            + "、".join(dict.fromkeys(matched_terms))
            + "。这是产品词关联，需核对其为实际经营产品而非客户、计划或经营范围。"
        )
    else:
        explanation.append(
            "节点关联已有单独资料依据，请查看产品、经营主体及报告期；不据此推断全部产品或供应关系。"
        )
    metrics = link["metrics"]
    if metrics:

        def year(m):
            return (
                int(m["period"][:4]),
                {"FY": 5, "Q4": 4, "Q3": 3, "H1": 2, "Q2": 2, "Q1": 1}[m["period"][5:]],
            )

        latest = max(metrics, key=year)["period"]
        latest_values = [m for m in metrics if m["period"] == latest]
        explanation.append(
            f"最近已取得的匹配期为 {latest}，涉及"
            + "、".join(dict.fromkeys(m["subject"] for m in latest_values))
            + "。各分部边界可能大于节点产品，不能把这些金额自动相加为节点收入。"
        )
        if len(latest_values) == 1 and latest_values[0]["share"] is not None:
            metric = latest_values[0]
            explanation.append(
                f"该披露分部占来源所给总收入的 {metric['share']:.2f}%；反映公司收入结构，属于"
                + ("较主要" if metric["share"] >= 50 else "部分")
                + "收入来源，不代表产业链市场份额。"
            )
        explanation.append("年度与半年度金额不能直接计算同比；分部样本规模不能自动认定市场龙头。")
    else:
        explanation.append(
            link.get("financial_status", "未取得该节点对应的产品分部口径")
            + "；不以市值或行业总营收代替节点收入。"
        )
    if not link["leaders"]:
        explanation.append(
            "尚无符合产品、地域、时期与来源要求的节点龙头证据，不由行业权重或主营词推定竞争排名。"
        )
    return explanation


def audit_analysis(doc):
    meaningful = [n for n in doc["nodes"] if n["key"] != "unassigned"]
    errors = []
    if doc.get("analysis_version") != 2:
        errors.append("尚未采用全行业专属经营分析")
    if {n["column"] for n in meaningful} != {0, 1, 2}:
        errors.append("缺少投入、核心或需求环节")
    for node in meaningful:
        if {a["id"] for a in node["analyses"]} != {"operating", "cash-and-risk"}:
            errors.append(node["key"] + "缺少经营或现金风险分析")
        if "具体龙头认定" not in node["competition"]:
            errors.append(node["key"] + "缺少竞争评价边界")
    if any(len(link.get("company_analysis", [])) < 2 for link in doc["stocks"]):
        errors.append("存在未解释的公司关联")
    return dict(
        passed=not errors,
        errors=errors,
        nodes=len(meaningful),
        analysis_paths=sum(len(n["analyses"]) for n in meaningful),
        company_links=len(doc["stocks"]),
    )
