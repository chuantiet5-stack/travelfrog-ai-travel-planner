"""
旅游推荐相似度计算模块。

用于计算：
1. 标签匹配相似度
2. 有序等级相似度
3. 多标签相似度

所有相似度统一返回 0~1。
"""


def split_tags(value):
    """将单值或多值标签统一转换为集合。"""
    return {
        item.strip()
        for item in str(value or "").replace("，", ",").replace("、", ",").split(",")
        if item.strip()
    }


def exact_similarity(user_value, spot_value):
    """
    精确匹配相似度。

    支持数据库字段包含多个标签，例如：
    用户：秋季
    景点：春季,秋季

    只要用户标签出现在景点标签集合中，就认为完全匹配。
    """
    user_tags = split_tags(user_value)
    spot_tags = split_tags(spot_value)

    if not user_tags or not spot_tags:
        return 0.0

    return 1.0 if user_tags & spot_tags else 0.0


def ordered_similarity(user_value, spot_value, ordered_values):
    """
    计算有序类别之间的相似度。

    支持景点字段存在多个标签的情况。

    例如预算：

        低预算
        中等预算
        高预算

    用户选择：
        中等预算

    景点：
        中等预算,高预算

    因为景点包含“中等预算”，所以相似度为 1.0。

    如果用户选择：
        低预算

    景点：
        中等预算,高预算

    则会选择距离用户最近的标签“中等预算”进行计算，
    而不是直接判定为 0。

    参数：
        user_value: 用户选择
        spot_value: 景点对应属性
        ordered_values: 有序类别列表

    返回：
        0~1
    """

    if user_value not in ordered_values:
        return 0.0

    # 景点属性支持多值标签
    spot_values = {
        item.strip()
        for item in str(spot_value or "")
        .replace("，", ",")
        .replace("、", ",")
        .split(",")
        if item.strip()
    }

    if not spot_values:
        return 0.0

    # 只保留合法的有序类别
    spot_indices = [
        ordered_values.index(value)
        for value in spot_values
        if value in ordered_values
    ]

    if not spot_indices:
        return 0.0

    user_index = ordered_values.index(user_value)

    max_distance = len(ordered_values) - 1

    if max_distance == 0:
        return 1.0

    # 多个标签中选择与用户最接近的一个
    min_distance = min(
        abs(user_index - spot_index)
        for spot_index in spot_indices
    )

    return 1 - min_distance / max_distance


def multi_label_similarity(user_value, spot_tags):
    """
    计算多标签相似度。

    支持用户和景点都存在多个标签。
    返回 0~1。
    """

    if not user_value or not spot_tags:
        return 0.0

    def split_tags(value):
        """
        统一处理：
        1. 单个字符串
        2. 多标签字符串
        3. set
        4. list
        5. tuple
        6. 中文逗号、中文顿号
        """

        # 如果已经是集合 / 列表 / 元组
        if isinstance(value, (set, list, tuple)):
            return {
                str(item).strip()
                for item in value
                if str(item).strip()
            }

        # 普通字符串
        return {
            item.strip()
            for item in str(value)
            .replace("，", ",")
            .replace("、", ",")
            .split(",")
            if item.strip()
        }

    # 用户标签
    user_tags = split_tags(user_value)

    # 景点标签
    spot_tag_set = split_tags(spot_tags)

    if not user_tags or not spot_tag_set:
        return 0.0

    # 求交集
    matched_tags = user_tags & spot_tag_set

    # 用户喜欢的标签中，有多少被景点命中
    return len(matched_tags) / len(user_tags)