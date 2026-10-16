# -*- coding: utf-8 -*-
"""盲解任务生成器（P1-7 第二解题者 · 上半场）
=====================================================
从题目清单生成"独立盲解"任务书，交给另一个模型/子代理独立作答，
用它的结果与官方答案交叉验证，降低单一模型的自证偏差。

用法:
  python make_solver_tasks.py questions.json -o solver_tasks [--per-task 8]
  # questions.json 来自 cut_questions.py 的输出（含每道题的文本快照）
输出:
  solver_tasks/task_01.md ...       每份任务书（可直接喂给 subagent/另一个模型）
  solver_tasks/index.json           任务 → 题号 映射（比对时用）

任务书契约（确保盲解干净）:
  - 不联网、不查原题、不参考答案；
  - 只输出「题N：<答案>」；如需过程每问最多一行；
  - 输出保存为 solver_answers.json（{ "1": "答案", ... }）。
"""
import argparse
import json
import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PROMPT_HEAD = """你是一位初中数学老师，请**独立盲解**下列题目：

【硬性要求】
1. 不要上网搜索，不要引用任何"参考答案"；
2. 做题前先自己完整推演一遍（可打草稿但不用输出过程）；
3. 输出格式严格如下（每行一题，不要多余解释）：
   题{qno}：<答案>
4. 多解题目写全所有解（用"、"分隔）；填空题带单位的要带单位；
5. 完成后把结果保存为 `solver_answers.json`（形如 {{"1": "231", "2": "B"}}）。

【题目清单】（共 {n} 题）
"""


def main():
    ap = argparse.ArgumentParser(description="盲解任务生成器")
    ap.add_argument("questions", help="cut_questions.py 输出的 questions.json")
    ap.add_argument("-o", "--out", default="solver_tasks")
    ap.add_argument("--per-task", type=int, default=8)
    args = ap.parse_args()

    qs = json.load(open(args.questions, encoding="utf-8-sig"))
    os.makedirs(args.out, exist_ok=True)

    index = []
    for t, i in enumerate(range(0, len(qs), args.per_task), 1):
        batch = qs[i:i + args.per_task]
        name = f"task_{t:02d}.md"
        lines = [PROMPT_HEAD.format(qno="{题号}", n=len(batch))]
        for q in batch:
            lines.append(f"题{q['qno']}（第{q['page']}页）：{q.get('text', '')[:400]}")
        path = os.path.join(args.out, name)
        open(path, "w", encoding="utf-8").write("\n".join(lines))
        index.append({"task": name, "qn": [q["qno"] for q in batch],
                      "pages": [q["page"] for q in batch]})
    json.dump(index, open(os.path.join(args.out, "index.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"生成 {len(index)} 份任务书 → {os.path.abspath(args.out)}")
    for it in index:
        print(f"  {it['task']}: 共{len(it['qn'])}题（第{it['pages'][0]}~{it['pages'][-1]}页，题号: "
              + ",".join(str(q) for q in it['qn'][:10]) + ("…" if len(it['qn']) > 10 else "") + "）")
    print("\n使用方法：把 task_XX.md 的内容发给另一个模型/子代理（不给它答案），")
    print("收集其输出为 solver_answers.json 后，运行 compare_answers.py 交叉验证。")


if __name__ == "__main__":
    main()
