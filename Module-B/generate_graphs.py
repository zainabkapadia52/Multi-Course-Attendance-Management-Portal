"""
Performance Analysis: Before vs After Indexing
===============================================
Generates comparison graphs and detailed analysis
"""

import json
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
from datetime import datetime

# Load results
with open('benchmark_results_before.json', 'r') as f:
    before = json.load(f)

with open('benchmark_results_after.json', 'r') as f:
    after = json.load(f)

# Extract data
queries_before = before['queries']
queries_after = after['queries']

# Prepare comparison data
comparison = {}
for query_name in queries_before:
    if 'error' not in queries_before[query_name] and 'error' not in queries_after.get(query_name, {}):
        b_time = queries_before[query_name]['mean']
        a_time = queries_after[query_name]['mean']
        improvement = ((b_time - a_time) / b_time * 100) if b_time > 0 else 0

        comparison[query_name] = {
            'before': b_time,
            'after': a_time,
            'improvement_pct': improvement,
            'improvement_ms': b_time - a_time,
            'before_median': queries_before[query_name]['median'],
            'after_median': queries_after[query_name]['median'],
        }

# Sort by improvement
sorted_comparison = sorted(comparison.items(), key=lambda x: x[1]['improvement_pct'], reverse=True)

# === SUMMARY STATISTICS ===
print("\n" + "="*90)
print("PERFORMANCE IMPROVEMENT SUMMARY")
print("="*90)

total_before = sum(q['before'] for q in comparison.values())
total_after = sum(q['after'] for q in comparison.values())
total_improvement = ((total_before - total_after) / total_before * 100) if total_before > 0 else 0

print(f"\nTotal Query Time (all {len(comparison)} queries):")
print(f"  Before: {total_before:.4f} ms")
print(f"  After:  {total_after:.4f} ms")
print(f"  Overall Improvement: {total_improvement:.2f}%")
print(f"  Time Saved: {total_before - total_after:.4f} ms")

print(f"\nAverage Query Time:")
print(f"  Before: {total_before/len(comparison):.4f} ms")
print(f"  After:  {total_after/len(comparison):.4f} ms")

# === TOP IMPROVEMENTS ===
print(f"\n" + "="*90)
print("TOP 5 QUERIES WITH MAXIMUM IMPROVEMENT")
print("="*90)

for idx, (name, data) in enumerate(sorted_comparison[:5], 1):
    print(f"\n{idx}. {name}")
    print(f"   Before: {data['before']:.4f} ms")
    print(f"   After:  {data['after']:.4f} ms")
    print(f"   Improvement: {data['improvement_pct']:.2f}% (saved {data['improvement_ms']:.4f} ms)")

# === QUERIES NEEDING ATTENTION ===
print(f"\n" + "="*90)
print("QUERIES STILL SLOW (>0.1 ms)")
print("="*90)

slow_queries = [name for name, data in comparison.items() if data['after'] > 0.1]
if slow_queries:
    for name in slow_queries:
        data = comparison[name]
        print(f"  - {name}: {data['after']:.4f} ms (improved {data['improvement_pct']:.1f}%)")
else:
    print("  All queries now run below 0.1 ms!")

# === FIGURE 1: Bar Chart Comparison ===
fig, axes = plt.subplots(2, 2, figsize=(16, 12))
fig.suptitle('Module B Performance Analysis: Before vs After Indexing', fontsize=16, fontweight='bold')

# Subplot 1: Mean query times
ax1 = axes[0, 0]
names = [n for n, _ in sorted_comparison]
before_times = [comparison[n]['before'] for n in names]
after_times = [comparison[n]['after'] for n in names]

x = np.arange(len(names))
width = 0.35

bars1 = ax1.bar(x - width/2, before_times, width, label='Before Indexing', color='#e74c3c', alpha=0.8)
bars2 = ax1.bar(x + width/2, after_times, width, label='After Indexing', color='#27ae60', alpha=0.8)

ax1.set_ylabel('Query Time (ms)', fontweight='bold')
ax1.set_title('Mean Query Times Comparison', fontweight='bold')
ax1.set_xticks(x)
ax1.set_xticklabels(names, rotation=45, ha='right', fontsize=9)
ax1.legend()
ax1.grid(axis='y', alpha=0.3)

# Add value labels on bars
for bars in [bars1, bars2]:
    for bar in bars:
        height = bar.get_height()
        ax1.text(bar.get_x() + bar.get_width()/2., height,
                f'{height:.4f}', ha='center', va='bottom', fontsize=7)

# Subplot 2: Improvement percentage
ax2 = axes[0, 1]
improvements = [comparison[n]['improvement_pct'] for n in names]
colors = ['#27ae60' if imp > 0 else '#e74c3c' for imp in improvements]

bars = ax2.barh(names, improvements, color=colors, alpha=0.8)
ax2.set_xlabel('Improvement (%)', fontweight='bold')
ax2.set_title('Performance Improvement by Query', fontweight='bold')
ax2.grid(axis='x', alpha=0.3)

# Add value labels
for bar in bars:
    width = bar.get_width()
    ax2.text(width, bar.get_y() + bar.get_height()/2.,
            f'{width:.1f}%', ha='left', va='center', fontsize=9, fontweight='bold')

# Subplot 3: Time savings
ax3 = axes[1, 0]
savings = [comparison[n]['improvement_ms'] for n in names]
colors = ['#27ae60' if s > 0 else '#e74c3c' for s in savings]

x_pos = np.arange(len(names))
bars = ax3.bar(x_pos, savings, color=colors, alpha=0.8)
ax3.set_ylabel('Time Saved (ms)', fontweight='bold')
ax3.set_title('Query Time Savings', fontweight='bold')
ax3.set_xticks(x_pos)
ax3.set_xticklabels(names, rotation=45, ha='right', fontsize=9)
ax3.grid(axis='y', alpha=0.3)

# Add value labels
for bar in bars:
    height = bar.get_height()
    ax3.text(bar.get_x() + bar.get_width()/2., height,
            f'{height:.4f}', ha='center', va='bottom', fontsize=7)

# Subplot 4: Before/After distribution
ax4 = axes[1, 1]
categories = ['<0.02ms', '0.02-0.05ms', '0.05-0.1ms', '>0.1ms']
before_counts = [0, 0, 0, 0]
after_counts = [0, 0, 0, 0]

for data in comparison.values():
    b_t = data['before']
    a_t = data['after']

    before_idx = 0 if b_t < 0.02 else (1 if b_t < 0.05 else (2 if b_t < 0.1 else 3))
    after_idx = 0 if a_t < 0.02 else (1 if a_t < 0.05 else (2 if a_t < 0.1 else 3))

    before_counts[before_idx] += 1
    after_counts[after_idx] += 1

x_cat = np.arange(len(categories))
width = 0.35

ax4.bar(x_cat - width/2, before_counts, width, label='Before', color='#e74c3c', alpha=0.8)
ax4.bar(x_cat + width/2, after_counts, width, label='After', color='#27ae60', alpha=0.8)

ax4.set_ylabel('Number of Queries', fontweight='bold')
ax4.set_title('Distribution of Query Times', fontweight='bold')
ax4.set_xticks(x_cat)
ax4.set_xticklabels(categories)
ax4.legend()
ax4.grid(axis='y', alpha=0.3)

plt.tight_layout()
plt.savefig('performance_comparison.png', dpi=300, bbox_inches='tight')
print(f"\n[OK] Graph saved: performance_comparison.png")

# === FIGURE 2: Detailed Metrics ===
fig2, axes2 = plt.subplots(2, 2, figsize=(16, 12))
fig2.suptitle('Detailed Performance Metrics', fontsize=16, fontweight='bold')

# Median comparison
ax1 = axes2[0, 0]
medians_before = [comparison[n]['before_median'] for n in names]
medians_after = [comparison[n]['after_median'] for n in names]

x = np.arange(len(names))
ax1.plot(x, medians_before, 'o-', linewidth=2, markersize=8, label='Before', color='#e74c3c')
ax1.plot(x, medians_after, 's-', linewidth=2, markersize=8, label='After', color='#27ae60')
ax1.set_ylabel('Median Time (ms)', fontweight='bold')
ax1.set_title('Median Query Times Trend', fontweight='bold')
ax1.set_xticks(x)
ax1.set_xticklabels(names, rotation=45, ha='right', fontsize=9)
ax1.legend()
ax1.grid(True, alpha=0.3)

# Performance gains pie chart
ax2 = axes2[0, 1]
improvements_list = [max(0.1, comparison[n]['improvement_pct']) for n in names]  # Ensure all positive
colors_pie = ['#27ae60' if comparison[n]['improvement_pct'] >= 50 else ('#f39c12' if comparison[n]['improvement_pct'] >= 25 else '#e74c3c') for n in names]

wedges, texts, autotexts = ax2.pie(improvements_list, labels=names, autopct='%1.1f%%',
                                     colors=colors_pie, startangle=90)
ax2.set_title('Improvement Distribution (by %)', fontweight='bold')
for text in texts:
    text.set_fontsize(8)
for autotext in autotexts:
    autotext.set_color('white')
    autotext.set_fontsize(8)
    autotext.set_fontweight('bold')

# Efficiency rating
ax3 = axes2[1, 0]
efficiency_ratings = []
efficiency_labels = []
efficiency_colors = []

for name, data in sorted_comparison:
    if data['improvement_pct'] >= 50:
        rating = 'Excellent'
        color = '#27ae60'
    elif data['improvement_pct'] >= 25:
        rating = 'Good'
        color = '#f39c12'
    elif data['improvement_pct'] > 0:
        rating = 'Fair'
        color = '#3498db'
    else:
        rating = 'No Change'
        color = '#95a5a6'

    efficiency_ratings.append(rating)
    efficiency_labels.append(name)
    efficiency_colors.append(color)

# Count ratings
rating_counts = {}
for rating in efficiency_ratings:
    rating_counts[rating] = rating_counts.get(rating, 0) + 1

# Create bar chart
rating_types = list(rating_counts.keys())
rating_values = list(rating_counts.values())
rating_color_map = {'Excellent': '#27ae60', 'Good': '#f39c12', 'Fair': '#3498db', 'No Change': '#95a5a6'}
rating_colors_chart = [rating_color_map.get(r, '#95a5a6') for r in rating_types]

ax3.bar(rating_types, rating_values, color=rating_colors_chart, alpha=0.8)
ax3.set_ylabel('Number of Queries', fontweight='bold')
ax3.set_title('Query Efficiency Rating', fontweight='bold')
ax3.grid(axis='y', alpha=0.3)

for i, (rt, rv) in enumerate(zip(rating_types, rating_values)):
    ax3.text(i, rv, str(rv), ha='center', va='bottom', fontweight='bold')

# Key metrics table
ax4 = axes2[1, 1]
ax4.axis('off')

metrics_data = [
    ['Total Queries', str(len(comparison))],
    ['Overall Improvement', f'{total_improvement:.2f}%'],
    ['Avg Before', f'{total_before/len(comparison):.4f} ms'],
    ['Avg After', f'{total_after/len(comparison):.4f} ms'],
    ['Total Time Saved', f'{total_before - total_after:.4f} ms'],
    ['Best Performer', f'{names[0]} ({improvements[0]:.1f}%)'],
    ['Still Slow (>0.1ms)', str(len(slow_queries))],
]

table = ax4.table(cellText=metrics_data, colLabels=['Metric', 'Value'],
                  cellLoc='center', loc='center', colWidths=[0.5, 0.5])
table.auto_set_font_size(False)
table.set_fontsize(11)
table.scale(1, 2)

# Style header
for i in range(2):
    table[(0, i)].set_facecolor('#34495e')
    table[(0, i)].set_text_props(weight='bold', color='white')

# Alternate row colors
for i in range(1, len(metrics_data) + 1):
    color = '#ecf0f1' if i % 2 == 0 else 'white'
    for j in range(2):
        table[(i, j)].set_facecolor(color)

plt.tight_layout()
plt.savefig('detailed_metrics.png', dpi=300, bbox_inches='tight')
print(f"[OK] Graph saved: detailed_metrics.png")

plt.close('all')
print("\nAll performance graphs generated successfully!")
