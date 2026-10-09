from app import preference_from_form


form_data = {
    "origin": "广州",

    "season": "秋季",
    "style_type": "小桥流水",
    "budget_level": "中等预算",
    "play_days": "2-3天",
    "people_type": "情侣",

    "priority_origin": "5",
    "priority_season": "3",
    "priority_style_type": "5",
    "priority_budget_level": "3",
    "priority_play_days": "3",
    "priority_people_type": "4",
}


pref = preference_from_form(form_data)

print("用户偏好：")
print(pref)

print("\n出发地：")
print(pref["origin"])

print("\n出发地重要程度：")
print(pref["priority"]["origin"])