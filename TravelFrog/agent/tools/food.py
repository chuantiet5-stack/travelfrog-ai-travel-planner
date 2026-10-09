from agent.tools.base import Tool


class FoodFilterTool(Tool):

    @property
    def name(self):
        return "food_filter"


    @property
    def description(self):
        return (
            "旅游规划专用美食过滤工具。"
			"当高德地图搜索返回餐饮POI后必须调用此工具。"
			"用于筛选适合游客体验的当地特色美食。"
			"自动删除肯德基、麦当劳、汉堡王等全国连锁快餐。"
			"优先保留当地老字号、地方菜馆、特色小吃、传统美食街。"
        )


    @property
    def parameters(self):

        return {
            "type": "object",
            "properties": {
                "foods": {
                    "type": "array",
                    "description": "高德返回的餐饮POI列表"
                }
            },
            "required": [
                "foods"
            ]
        }


    async def execute(self, foods):

        blacklist = [
			# 国际连锁快餐
			"肯德基",
			"KFC",
			"麦当劳",
			"McDonald",
			"汉堡王",
			"必胜客",
			"星巴克",

			# 快餐类型
			"快餐",
			"炸鸡",
			"汉堡",
			"奶茶",
			"便利店",

			# 便利品牌
			"711",
			"全家",
			"罗森",
        ]


        result = []


        for item in foods:

            name = item.get(
                "name",
                ""
            )


            # 过滤连锁
            if any(
                word in name
                for word in blacklist
            ):
                continue


            result.append(
                item
            )


        return str(result[:10])