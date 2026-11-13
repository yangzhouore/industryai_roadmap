import json
from pathlib import Path
p = Path(__file__).with_name('issues.json')
issues = json.loads(p.read_text(encoding='utf-8'))
titles = ['从模型到工厂现场', '当自动化遇上判断力', '工业前沿信号']
story_titles = ['走近工业视觉检测', '机器人与操作员之间的交接', '预测需求，承认不确定性']
summaries = ['此模拟试点探索工程师如何在产线上审核模型告警。', '虚构工作站展示人工审核、任务边界和安全恢复。', '模拟研究简报讨论如何在预测中明确表达不确定性。']
for i, issue in enumerate(issues):
    issue['title']['zh'] = titles[i]
    issue['introduction']['zh'] = '关于工业人工智能实践问题的演示期刊。以下所有故事和来源均为明确标注的模拟内容。'
    for j, story in enumerate(issue['stories']):
        story['title']['zh'] = story_titles[j]
        story['summary']['zh'] = summaries[j]
        story['why']['zh'] = '编辑分析：得出结论前，应审视工作流程、证据和部署约束。'
        story['limitation']['zh'] = '仅供演示，不代表真实部署、公司或性能结果。'
        issue['sources'][j]['excerpt']['zh'] = summaries[j]
p.write_text(json.dumps(issues, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
