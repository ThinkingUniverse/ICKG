import json
import random

# 读取JSON文件
with open(r'data\pubmed_output\merge\PubMed_abstract_2016_01_01_2026_03_31.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

# 打乱数据
random.shuffle(data)

# 抽取前5000条
sampled_data = data[:5000]

# 保存结果
output_path = r'data\pubmed_output\random_sampling\PubMed_abstract_sampled_5000_1.json'
with open(output_path, 'w', encoding='utf-8') as f:
    json.dump(sampled_data, f, ensure_ascii=False, indent=2)

print(f"原始数据量: {len(data)}")
print(f"抽取数据量: {len(sampled_data)}")
print(f"已保存至: {output_path}")