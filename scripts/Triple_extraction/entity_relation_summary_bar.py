#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
统计三元组数据中的实体类型、关系类型和唯一实体
"""

import json
import pandas as pd
import matplotlib.pyplot as plt
from collections import defaultdict, Counter
from pathlib import Path

# 设置中文字体支持
plt.rcParams['font.sans-serif'] = ['SimHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

def load_triples(jsonl_path):
    """
    加载JSONL文件中的三元组数据
    """
    triples = []
    with open(jsonl_path, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                try:
                    triple = json.loads(line)
                    triples.append(triple)
                except json.JSONDecodeError:
                    print(f"警告：无法解析行：{line}")
                    continue
    return triples


def count_entity_types(triples):
    """
    统计实体类型出现的次数（head_type 和 tail_type）
    """
    type_counter = Counter()
    
    for triple in triples:
        if 'head_type' in triple:
            type_counter[triple['head_type']] += 1
        if 'tail_type' in triple:
            type_counter[triple['tail_type']] += 1
    
    return type_counter


def count_relation_types(triples):
    """
    统计关系类型出现的次数
    """
    relation_counter = Counter()
    
    for triple in triples:
        if 'relation' in triple:
            relation_counter[triple['relation']] += 1
    
    return relation_counter


def count_unique_entities(triples):
    """
    统计唯一的实体实例个数
    """
    unique_heads = set()
    unique_tails = set()
    
    for triple in triples:
        if 'head' in triple:
            unique_heads.add(triple['head'])
        if 'tail' in triple:
            unique_tails.add(triple['tail'])
    
    all_unique_entities = unique_heads | unique_tails
    
    return {
        'unique_heads': len(unique_heads),
        'unique_tails': len(unique_tails),
        'total_unique': len(all_unique_entities),
        'head_entities': unique_heads,
        'tail_entities': unique_tails
    }


def save_to_tsv(counter_dict, output_path, title_col='类型', count_col='计数'):
    """
    将计数字典保存为TSV文件
    """
    df = pd.DataFrame([
        {title_col: key, count_col: count}
        for key, count in sorted(counter_dict.items(), key=lambda x: x[1], reverse=True)
    ])
    df.to_csv(output_path, sep='\t', index=False, encoding='utf-8')
    print(f"已保存：{output_path}")
    return df


def generate_bar_chart(counter_dict, output_path, title, xlabel, ylabel):
    """
    生成柱状图并保存为PDF
    """
    # 按计数升序排序（最少的在下面，最多的在上面）
    sorted_items = sorted(counter_dict.items(), key=lambda x: x[1], reverse=False)
    
    if not sorted_items:
        print(f"警告：{title}没有数据")
        return
    
    keys, values = zip(*sorted_items)
    
    # 根据项目数量调整图表大小
    num_items = len(keys)
    fig_height = max(8, num_items * 0.3)
    
    fig, ax = plt.subplots(figsize=(12, fig_height))
    
    # 绘制横向柱状图以便显示长标签
    bars = ax.barh(range(len(keys)), values, color='steelblue')
    
    # 在每个柱子上添加数值标签
    for i, (bar, value) in enumerate(zip(bars, values)):
        ax.text(value + 0.5, i, str(value), va='center', fontsize=9)
    
    ax.set_yticks(range(len(keys)))
    ax.set_yticklabels(keys, fontsize=10)
    ax.set_xlabel(ylabel, fontsize=12)
    ax.set_title(title, fontsize=14, fontweight='bold')
    ax.grid(axis='x', alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(output_path, format='pdf', dpi=300, bbox_inches='tight')
    print(f"已保存：{output_path}")
    plt.close()


def main():
    """
    主函数
    """
    # 定义路径
    script_dir = Path(__file__).parent
    data_dir = Path(script_dir).parent.parent / 'data' / 'Fine_tuning_dataset'
    jsonl_file = data_dir / 'triples_baichuan_m3_plus.jsonl'
    
    # 创建结果输出目录
    output_dir = Path(script_dir).parent.parent / 'results' / 'entity_relation_summary_bar'
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 检查输入文件是否存在
    if not jsonl_file.exists():
        print(f"错误：找不到文件 {jsonl_file}")
        return
    
    print(f"读取文件：{jsonl_file}")
    
    # 加载三元组数据
    triples = load_triples(str(jsonl_file))
    print(f"总三元组数：{len(triples)}")
    
    # 统计实体类型
    print("\n=== 统计实体类型 ===")
    entity_type_counter = count_entity_types(triples)
    entity_type_df = save_to_tsv(
        entity_type_counter,
        output_dir / 'entity_types_summary.tsv',
        title_col='实体类型',
        count_col='出现次数'
    )
    print(f"实体类型总数：{len(entity_type_counter)}")
    print(entity_type_df.to_string(index=False))
    
    # 生成实体类型柱状图
    generate_bar_chart(
        entity_type_counter,
        output_dir / 'entity_types_summary.pdf',
        '实体类型分布',
        '实体类型',
        '出现次数'
    )
    
    # 统计关系类型
    print("\n=== 统计关系类型 ===")
    relation_counter = count_relation_types(triples)
    relation_df = save_to_tsv(
        relation_counter,
        output_dir / 'relation_types_summary.tsv',
        title_col='关系类型',
        count_col='出现次数'
    )
    print(f"关系类型总数：{len(relation_counter)}")
    print(relation_df.to_string(index=False))
    
    # 生成关系类型柱状图（只显示出现次数 >= 50 的关系类型）
    filtered_relation_counter = {k: v for k, v in relation_counter.items() if v >= 50}
    generate_bar_chart(
        filtered_relation_counter,
        output_dir / 'relation_types_summary.pdf',
        '关系类型分布 (出现次数 >= 50)',
        '关系类型',
        '出现次数'
    )
    
    # 统计唯一实体
    print("\n=== 统计唯一实体 ===")
    entity_stats = count_unique_entities(triples)
    print(f"唯一head实体数：{entity_stats['unique_heads']}")
    print(f"唯一tail实体数：{entity_stats['unique_tails']}")
    print(f"总唯一实体数：{entity_stats['total_unique']}")
    
    # 保存唯一实体统计摘要
    entity_summary = pd.DataFrame([
        {'统计项目': '三元组总数', '数量': len(triples)},
        {'统计项目': '实体类型总数', '数量': len(entity_type_counter)},
        {'统计项目': '关系类型总数', '数量': len(relation_counter)},
        {'统计项目': '唯一head实体数', '数量': entity_stats['unique_heads']},
        {'统计项目': '唯一tail实体数', '数量': entity_stats['unique_tails']},
        {'统计项目': '总唯一实体数', '数量': entity_stats['total_unique']},
    ])
    entity_summary.to_csv(
        output_dir / 'entity_summary_stats.tsv',
        sep='\t',
        index=False,
        encoding='utf-8'
    )
    print(f"\n已保存摘要统计到：{output_dir / 'entity_summary_stats.tsv'}")
    print(entity_summary.to_string(index=False))
    
    print("\n=== 统计完成 ===")
    print(f"输出文件位置：{output_dir}")
    print("生成的文件：")
    print("  - entity_types_summary.tsv (实体类型统计表)")
    print("  - entity_types_summary.pdf (实体类型柱状图)")
    print("  - relation_types_summary.tsv (关系类型统计表)")
    print("  - relation_types_summary.pdf (关系类型柱状图)")
    print("  - entity_summary_stats.tsv (实体摘要统计表)")


if __name__ == '__main__':
    main()
