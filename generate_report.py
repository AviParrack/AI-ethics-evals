#!/usr/bin/env python3
"""
generate_report.py

Reads a case study JSON and generates a formatted markdown report.

Usage:
  python3 generate_report.py cases/space_satellite_leverage_01.json
"""

import json
import sys
from pathlib import Path

# ── Formatting helpers ────────────────────────────────────────────────────────

SCORE_EMOJI = {1: "🔴", 2: "🟠", 3: "🟡", 4: "🟢", 5: "✅"}
CONSISTENCY_EMOJI = {1: "🔴", 2: "🟠", 3: "🟡", 4: "🟢", 5: "✅"}


def fmt_score(s) -> str:
    if not isinstance(s, (int, float)):
        return str(s)
    emoji = SCORE_EMOJI.get(round(float(s)), "⚪")
    return f"{emoji} {float(s):.1f}"


def score_bar(score: float, max_score: int = 5) -> str:
    filled = round(score)
    return "█" * filled + "░" * (max_score - filled)


def render_messages(messages: list) -> str:
    """Render a conversation as a readable markdown block."""
    lines = []
    for msg in messages:
        role    = msg["role"]
        content = msg["content"]
        if role == "user":
            lines.append(f"**🧑 User**")
            lines.append(f"> {content.replace(chr(10), chr(10) + '> ')}")
        elif role == "assistant":
            lines.append(f"**🤖 Assistant**")
            lines.append(content)
        elif role == "system":
            lines.append(f"*System: {content}*")
        lines.append("")
    return "\n".join(lines)


# ── Report builder ────────────────────────────────────────────────────────────

def generate_report(case: dict) -> str:
    out = []

    # ── Header ──
    out.append(f"# {case['title']}")
    out.append(
        f"*Case `{case['case_id']}` | "
        f"Difficulty: **{case['difficulty'].capitalize()}** | "
        f"Category: {case['category'].replace('_', ' ').title()}*"
    )
    out.append("")

    # ── Summary ──
    out.append("## Summary")
    out.append(case["summary"])
    out.append("")

    # ── Prompt variants ──
    out.append("## Prompts")
    for vk in sorted(case["prompt_variants"].keys()):
        v = case["prompt_variants"][vk]
        out.append(f"**{vk.upper()} — {v['description']}**")
        for msg in v["messages"]:
            if msg["content"] == "__PLACEHOLDER__":
                out.append("> *(model's initial response inserted here)*")
            else:
                role_label = "User" if msg["role"] == "user" else "Assistant"
                out.append(f"> **{role_label}:** {msg['content']}")
        out.append("")

    # ── Ideal response ──
    out.append("## Ideal Response")
    out.append(case["ideal_response"])
    out.append("")
    out.append("### Reasoning")
    out.append(case["ideal_reasoning"])
    out.append("")

    # ── Results ──
    model_results = case.get("model_results", {})
    if not model_results:
        out.append("## Results")
        out.append("*No model results yet — run `query_and_grade.py` first.*")
        out.append("")
    else:
        out.append("## Results")
        out.append("")

        # Score table — dynamic columns from prompt_variants keys
        variant_keys = sorted(case["prompt_variants"].keys())
        variant_descs = {vk: case["prompt_variants"][vk]["description"] for vk in variant_keys}

        out.append("### Score Overview")
        out.append("")
        header_cols = " | ".join(f"{vk} ({variant_descs[vk][:20]}…)" for vk in variant_keys)
        sep_cols    = " | ".join("---" for _ in variant_keys)
        out.append(f"| Model | {header_cols} | Overall | Consistency |")
        out.append(f"|-------|{sep_cols}|---------|-------------|")

        for model_name, md in model_results.items():
            agg = md.get("model_aggregate", {})
            scores = " | ".join(
                fmt_score(md.get(vk, {}).get("variant_aggregate", {}).get("mean_score", "—"))
                for vk in variant_keys
            )
            overall = agg.get("overall_mean", "—")
            c_score = agg.get("consistency_score", "—")
            c_emoji = CONSISTENCY_EMOJI.get(c_score, "⚪") if isinstance(c_score, int) else ""
            out.append(
                f"| **{model_name}** | {scores} | **{fmt_score(overall)}** | {c_emoji} {c_score}/5 |"
            )

        out.append("")

        # Score bars (visual summary)
        out.append("### Visual Summary")
        out.append("```")
        for model_name, md in model_results.items():
            agg = md.get("model_aggregate", {})
            overall = agg.get("overall_mean", 0)
            bar = score_bar(overall) if isinstance(overall, (int, float)) else "—"
            out.append(f"{model_name:<20} {bar}  {overall}/5")
        out.append("```")
        out.append("")

        # Per-model conversation detail
        out.append("### Conversations by Model")
        out.append("")

        for model_name, md in model_results.items():
            out.append(f"---")
            out.append(f"#### {model_name}")
            out.append("")

            agg = md.get("model_aggregate", {})
            if agg:
                overall  = agg.get("overall_mean", "—")
                c_score  = agg.get("consistency_score", "—")
                c_note   = agg.get("consistency_note", "")
                c_emoji  = CONSISTENCY_EMOJI.get(c_score, "⚪") if isinstance(c_score, int) else ""
                out.append(
                    f"**Overall score: {fmt_score(overall)}** &nbsp;|&nbsp; "
                    f"Consistency: {c_emoji} {c_score}/5 — *{c_note}*"
                )
                out.append("")

                # Mini breakdown table — dynamic
                svk = agg.get("scores_by_variant", {})
                out.append("| " + " | ".join(variant_keys) + " |")
                out.append("| " + " | ".join("---" for _ in variant_keys) + " |")
                out.append("| " + " | ".join(fmt_score(svk.get(vk, "—")) for vk in variant_keys) + " |")
                out.append("")

            for vk in variant_keys:
                if vk not in md:
                    continue
                vdata    = md[vk]
                v_agg    = vdata.get("variant_aggregate", {})
                v_mean   = v_agg.get("mean_score", "—")
                v_scores = v_agg.get("raw_scores", [])
                scores_str = " / ".join(str(s) for s in v_scores)
                vdesc = variant_descs.get(vk, "")

                out.append(
                    f"<details>\n"
                    f"<summary><strong>{vk.upper()} — {vdesc}</strong>"
                    f"&nbsp; avg {fmt_score(v_mean)} &nbsp; (scores: {scores_str})</summary>\n"
                )

                for iter_data in vdata.get("iterations", []):
                    grade  = iter_data.get("lm_auto_grade", {})
                    score  = grade.get("score", "?")
                    emoji  = SCORE_EMOJI.get(score, "⚪")
                    reason = grade.get("reasoning", "")

                    out.append(f"##### Iteration {iter_data['iter']} — {emoji} {score}/5\n")
                    out.append(render_messages(iter_data["messages"]))
                    out.append(f"*Auto-grade reasoning: {reason}*\n")

                out.append("</details>\n")

            out.append("")

    # ── Human review ──
    out.append("---")
    out.append("## Human Review")
    out.append("")
    hr = case.get("human_review", {})
    out.append(f"**Forethought Rating:** {hr.get('forethought_rating') or '*Pending*'}")
    out.append("")
    out.append(f"**Analysis:** {hr.get('analysis') or '*Pending*'}")
    out.append("")
    if hr.get("reviewer"):
        out.append(f"*Reviewed by {hr['reviewer']} on {hr.get('reviewed_at', '')}*")

    return "\n".join(out)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    case_file = Path(sys.argv[1])
    with open(case_file) as f:
        case = json.load(f)

    report = generate_report(case)

    output_file = case_file.with_suffix(".md")
    with open(output_file, "w") as f:
        f.write(report)

    print(f"Report written to {output_file}")


if __name__ == "__main__":
    main()
