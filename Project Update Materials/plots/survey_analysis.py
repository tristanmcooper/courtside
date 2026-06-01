# Single-cell Jupyter notebook code to reproduce the survey analysis
# Drop this into one cell in a notebook in the same folder as the survey CSV

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from collections import Counter

# === LOAD ===
CSV = "/Users/tristancooper/Desktop/ECE 284 Hardware Sensing/plots/ECE 284 ML Hardware Project Beach Volleyball Athletic Sensing Survey (Responses) - Form Responses 1.csv"
df = pd.read_csv(CSV)
df.columns = [c.strip() for c in df.columns]

# === FACTOR RATINGS ===
factor_cols = [c for c in df.columns if 'Rate how much' in c]
clean = [c.split('[')[1].rstrip(']') for c in factor_cols]
fdf = df[factor_cols].copy()
fdf.columns = clean
fdf = fdf.apply(pd.to_numeric, errors='coerce')
means = fdf.mean().sort_values(ascending=True)
stds = fdf.std()

# === SUMMARY STATS ===
print(f"N = {len(df)}")
print(f"\nLevel:\n{df['What level do you play at?'].value_counts()}")
print(f"\nRole:\n{df['Are you a blocker or defender'].value_counts()}")
print(f"\nYears playing:\n{df['How long have you been playing'].value_counts()}")
skill_col = [c for c in df.columns if 'Rate your current beach volleyball skill' in c][0]
skill = pd.to_numeric(df[skill_col], errors='coerce')
print(f"\nSkill 1-10: mean={skill.mean():.2f}, range={skill.min()}-{skill.max()}")
interest_col = [c for c in df.columns if 'After a session' in c][0]
print(f"\nInterest in tool:\n{df[interest_col].value_counts()}")

# === PLOT ===
SHORT = {
    'Sleep quality the night before': 'Sleep (night before)',
    'Sleep quality TWO nights before': 'Sleep (2 nights before)',
    'Time of day played': 'Time of day',
    'Overall recovery / how tired you feel': 'Recovery / tiredness',
    'Sun exposure / sand temperature': 'Sun / sand temp',
    'Mental state / confidence going in': 'Mental state / confidence',
    'Communication with your partner': 'Partner communication',
    "Who you're playing AGAINST": 'Opponent',
    'Who you play WITH': 'Partner',
    'What you ate that day': 'Food that day',
    'Noise levels around court': 'Court noise',
    'Speed of play (slow to serve / lots of shagging)': 'Pace of play',
    'Warm up': 'Warm-up',
}
labels = [SHORT.get(f, f) for f in means.index]

colors = []
n = len(means)
for i in range(n):
    if i >= n - 5:        # top 5
        colors.append('#c05a3a')
    elif i < 3:           # bottom 3
        colors.append('#aaaaaa')
    else:
        colors.append('#6a8caf')

fig, ax = plt.subplots(figsize=(8.5, 5))
ax.barh(labels, means.values, xerr=[stds[f] for f in means.index],
        color=colors, edgecolor='black', linewidth=0.5,
        error_kw={'lw': 0.8, 'capsize': 3, 'ecolor': '#444'})
ax.set_xlabel('Mean perceived impact (1 = no effect, 5 = huge effect)', fontsize=10)
ax.set_title(f'Player-rated factor importance (N = {len(df)})', fontsize=11)
ax.set_xlim(1, 5)
ax.axvline(3.0, color='gray', linestyle=':', linewidth=0.6, alpha=0.7)
ax.set_axisbelow(True)
ax.grid(axis='x', alpha=0.3)
for spine in ['top', 'right']:
    ax.spines[spine].set_visible(False)
plt.tight_layout()
plt.savefig('factor_rankings.pdf', bbox_inches='tight')
plt.savefig('factor_rankings.png', dpi=200, bbox_inches='tight')
plt.show()