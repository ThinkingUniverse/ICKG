# Verify that the saved LoRA adapter tokenizer renders an inference prompt
# whose tail matches the training distribution.
# 校验：训练完成后 adapter/ 目录里的 tokenizer，在默认 add_generation_prompt=True 调用下，
# 推理 prompt 末尾应当是 `<|im_start|>assistant\n`（与训练分布对齐）。
# 若末尾出现 `<think>` 相关内容，则说明被显式传入了 thinking_mode 或模板被改坏，
# 模型会被送进训练里从未见过的上下文。
import argparse
import json
from pathlib import Path

from transformers import AutoTokenizer

EXPECTED_TAIL = '<|im_start|>assistant\n'


def main() -> None:
    parser = argparse.ArgumentParser(description='校验 adapter tokenizer 的推理 prompt 末尾是否与训练分布对齐')
    parser.add_argument('--adapter-dir', '-a', required=True, help='adapter 目录路径（含 tokenizer_config.json）')
    parser.add_argument('--sample-jsonl', '-s', default=None,
                        help='可选：从该 jsonl 取首条样本做端到端验证（每行含 messages 字段）')
    parser.add_argument('--strict-thinking-mode-check', action='store_true',
                        help='额外检查 thinking_mode=off 路径会产生 <think>，提醒不要使用')
    args = parser.parse_args()

    adapter = Path(args.adapter_dir)
    if not (adapter / 'tokenizer_config.json').exists():
        raise SystemExit(f'[错误] {adapter} 下缺少 tokenizer_config.json')

    tok = AutoTokenizer.from_pretrained(str(adapter), trust_remote_code=True)
    if not tok.chat_template:
        raise SystemExit('[错误] tokenizer.chat_template 为空')

    # 用一条最小消息测末尾
    msgs_min = [
        {'role': 'system', 'content': '你是一个三元组抽取助手。'},
        {'role': 'user', 'content': '示例输入。'},
    ]
    prompt = tok.apply_chat_template(msgs_min, tokenize=False, add_generation_prompt=True)
    if not prompt.endswith(EXPECTED_TAIL):
        raise SystemExit(
            f'[失败] prompt 末尾不是预期的 {EXPECTED_TAIL!r}\n'
            f'        实际末尾 60 字符：{prompt[-60:]!r}\n'
            f'        若末尾含 <think>，调用侧很可能误传 thinking_mode；或 tokenizer 被改坏。'
        )
    print(f'[OK] 默认调用 prompt 末尾为 {EXPECTED_TAIL!r}，与训练分布对齐。')

    if args.strict_thinking_mode_check:
        prompt_off = tok.apply_chat_template(
            msgs_min, tokenize=False, add_generation_prompt=True, thinking_mode='off')
        if '<think>' in prompt_off[-30:]:
            print('[提醒] thinking_mode="off" 会在 prompt 末尾注入 <think>\n\n —— 该路径未训练，不应使用。')

    if args.sample_jsonl:
        path = Path(args.sample_jsonl)
        with path.open('r', encoding='utf-8') as f:
            sample = json.loads(f.readline())
        msgs = [m for m in sample['messages'] if m['role'] in ('system', 'user')]
        prompt_real = tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
        if not prompt_real.endswith(EXPECTED_TAIL):
            raise SystemExit(f'[失败] 真实样本 prompt 末尾不对齐：{prompt_real[-60:]!r}')
        print(f'[OK] 真实样本 prompt 末尾同样对齐（取自 {path.name}）。')

    print('[完成] adapter tokenizer 与训练分布在 prompt 边界处对齐校验通过。')


if __name__ == '__main__':
    main()
