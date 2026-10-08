"""旧六要素（ext.*）与五区表单（elements.区.*）的双向映射（PRD §4.4、概念模型 §6）。

- 存量草稿 elements 为空时按本映射从 ext 兼容读取（概念模型 §6.2：无需数据回填）；
- 新写入以 elements 为主，ext 保留兼容副本（P0 双写过渡的反向，供 export 等旧读取方使用）；
- 旧 optional/subtype 字段（relatedSystem、devFeatures 等）已被 D 区通用要素覆盖，不回迁，原样留在 ext。
"""

# 旧 ext key → (区, 新要素 key)
LEGACY_TO_ZONE: dict[str, tuple[str, str]] = {
    "techSubtype": ("A", "techSubtype"),
    "businessScenario": ("C", "useScenario"),
    "valueImpact": ("B", "businessValue"),
    "acceptanceCriteria": ("D", "acceptanceCriteria"),
}

# (区, 新要素 key) → 旧 ext key（LEGACY_TO_ZONE 的逆映射）
ZONE_TO_LEGACY: dict[tuple[str, str], str] = {zone_key: legacy for legacy, zone_key in LEGACY_TO_ZONE.items()}


def elements_from_legacy(ext: dict | None) -> dict:
    """存量 ext 结构 → 五区 elements 结构（仅映射六要素，其余 ext key 忽略）。"""
    result: dict[str, dict] = {}
    for legacy_key, (zone, key) in LEGACY_TO_ZONE.items():
        value = (ext or {}).get(legacy_key)
        if value is not None:
            result.setdefault(zone, {})[key] = value
    return result


def legacy_from_elements(elements: dict | None) -> dict:
    """五区 elements 结构 → 旧 ext 兼容副本（仅六要素；其余新要素无旧位，不生成）。"""
    result: dict = {}
    for (zone, key), legacy_key in ZONE_TO_LEGACY.items():
        value = ((elements or {}).get(zone) or {}).get(key)
        if value is not None:
            result[legacy_key] = value
    return result
