import pandas as pd
import matplotlib.pyplot as plt

# Load population data
df = pd.read_csv("data/processed/municipal_population_2000_2024.csv")

# Define population bins
bins = [0, 5000, 20000, 50000, float("inf")]
labels = ["Under 5k", "5k-20k", "20k-50k", "50k+"]

df["population_bin"] = pd.cut(
    df["population"],
    bins=bins,
    labels=labels,
    right=False
)

# 1. Frequency of each bin in 2024
counts_2024 = (
    df[df["year"] == 2024]["population_bin"]
    .value_counts()
    .reindex(labels, fill_value=0)
)

print("Municipalities by population bin (2024):")
print(counts_2024)
print("\nPercentages:")
print((counts_2024 / counts_2024.sum() * 100).round(1))

plt.figure(figsize=(9, 5))
counts_2024.plot(kind="bar")
plt.title("Massachusetts Municipalities by Population Size (2024)")
plt.xlabel("Population bin")
plt.ylabel("Number of municipalities")
plt.xticks(rotation=0)
plt.tight_layout()
plt.show()

# 2. Frequency of each bin over time (2010-2024)
yearly_counts = (
    df[df["year"].between(2010, 2024)]
    .groupby(["year", "population_bin"], observed=False)
    .size()
    .unstack(fill_value=0)
    .reindex(columns=labels, fill_value=0)
)

print("\nPopulation-bin frequencies by year:")
print(yearly_counts)

plt.figure(figsize=(11, 6))

for label in labels:
    plt.plot(
        yearly_counts.index,
        yearly_counts[label],
        marker="o",
        label=label
    )

plt.title("Massachusetts Municipalities by Population Bin (2010-2024)")
plt.xlabel("Year")
plt.ylabel("Number of municipalities")
plt.legend(title="Population")
plt.grid(alpha=0.3)
plt.tight_layout()
plt.show()