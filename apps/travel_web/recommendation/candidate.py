"""
旅游推荐候选召回模块。

职责：

1. 接收基础匹配算法计算结果
2. 对景点按照基础匹配分数排序
3. 截取 Top-N 候选
4. 将候选交给后续 Agent

注意：

这里不负责最终推荐。
这里只负责“候选召回”。
"""


def select_top_candidates(results, top_n=5):
    """
    从基础匹配结果中选择 Top-N 候选。

    参数：
        results:
            基础匹配算法产生的景点结果列表

        top_n:
            候选数量，默认 5

    返回：
        排序后的 Top-N 候选
    """

    if not results:
        return []

    # 按基础匹配分数从高到低排序
    sorted_results = sorted(
        results,
        key=lambda item: (
            -item["score"],
            item["spot"]["id"],
        ),
    )

    # 防止 top_n 输入异常
    try:
        top_n = int(top_n)
    except (TypeError, ValueError):
        top_n = 5

    top_n = max(1, top_n)

    return sorted_results[:top_n]