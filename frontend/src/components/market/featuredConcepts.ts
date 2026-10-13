import type { Concept } from "../../api";

const featuredNames = [
  "AIGC概念",
  "多模态AI",
  "AI医疗",
  "AI眼镜",
  "机器视觉",
  "人脑工程",
  "算力租赁",
  "液冷服务",
  "云计算",
  "大数据",
  "数据要素",
  "信创",
  "信息安全",
  "工业软件",
  "工业互联",
  "华为鸿蒙",
  "量子科技",

  "存储芯片",
  "MCU芯片",
  "先进封装",
  "光刻机",
  "三代半导",
  "CPO概念",
  "光通信",
  "PCB概念",

  "固态电池",
  "钠电池",
  "锂矿",
  "充电桩",
  "高压快充",
  "换电概念",
  "电池回收",
  "特斯拉",
  "小米汽车",
  "飞行汽车",
  "车联网",

  "智能电网",
  "特高压",
  "虚拟电厂",
  "核电核能",
  "可控核变",
  "碳中和",
  "钙钛矿",
  "燃料电池",

  "卫星导航",
  "军工信息",
  "大飞机",
  "工业母机",
  "高端装备",
  "减速器",

  "创新药",
  "CXO概念",
  "合成生物",
  "基因概念",
  "生物疫苗",
  "减肥药",

  "跨境电商",
  "新零售",
  "预制菜",
  "宠物经济",
  "旅游概念",
  "种业",
  "稀土永磁",
  "黄金概念",
  "数字货币",
  "区块链",
];

const featuredOrder = new Map(
  featuredNames.map((name, index) => [name, index]),
);

export function featuredConcepts(
  concepts: Concept[],
  selected: string,
): Concept[] {
  return concepts
    .filter(
      (concept) =>
        concept.fetched_at &&
        (featuredOrder.has(concept.name) || concept.id === selected),
    )
    .sort(
      (left, right) =>
        (featuredOrder.get(left.name) ?? featuredNames.length) -
        (featuredOrder.get(right.name) ?? featuredNames.length),
    );
}
