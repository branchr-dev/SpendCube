# Procurement Spend Cube Dashboard Blueprint (V1)

## Objective

Use this as guidance to review the visualisations for the **V1 dashboard suite**. Do not take it all for gospel, but leverage some of the inspiration for key visualations. The goal is to build a procurement spend cube that goes beyond simple spend reporting and helps users identify **pricing variation, supplier negotiation opportunities, and working capital opportunities**.


The goal of V1 is to help a procurement user answer four core questions:

1. **Where are we spending money?**
2. **Where is price variation unusually high?**
3. **Where do we appear to be overpaying relative to internal benchmarks?**
4. **Which suppliers or items should we target first for negotiation?**

---

## Design principles for V1

A few principles should guide the dashboard design:

### 1. Move beyond descriptive reporting
The dashboard should not just show total spend by category or supplier. It should help users uncover **potential negotiation opportunities** and **areas of inconsistency**.

### 2. Prioritise explainable analytics
Use visuals and methods that buyers can understand and defend in conversation. Avoid overly complex analytics in V1 unless the output is intuitive.

### 3. Show ranges, not false precision
When highlighting opportunities, it is better to show a **range of plausible savings outcomes** than a single highly precise number that may not be robust.

### 4. Normalisation matters
All price comparisons should be based on the best available normalization logic, including:
- unit of measure conversion
- currency normalization
- time period alignment
- pack size / quantity normalization
- comparable specification grouping where possible

### 5. Separate observation from conclusion
The dashboard should distinguish between:
- observed price variation
- modeled opportunity
- benchmark comparison

This helps build trust in the outputs.

---

# Recommended V1 dashboard pages

For V1, I would recommend **four core dashboard pages**:

1. **Executive Spend & Opportunity Overview**
2. **Category / Item Price Diagnostics**
3. **Supplier Negotiation View**
4. **Working Capital & Payment Terms View**

---

# 1. Executive Spend & Opportunity Overview

This is the landing page. It should orient the user toward the biggest areas of value without overwhelming them.

## Key visuals

### A. Spend concentration chart
**Visual:** Sorted bar chart with cumulative line  
**Shows:** Spend by supplier or category, ordered from largest to smallest

**Why it is useful:**
- Shows where spend is concentrated
- Helps identify whether the opportunity is in a few strategic suppliers or in fragmented tail spend
- Gives a quick sense of where deeper analysis is worthwhile

---

### B. Category x business unit heatmap
**Visual:** Heatmap  
**Shows:** Spend intensity by category and business unit / plant / geography

**Why it is useful:**
- Highlights fragmented buying across the organisation
- Helps identify areas where similar items may be sourced differently across sites
- Can reveal aggregation opportunities or inconsistent category management

---

### C. Opportunity prioritisation scatter
**Visual:** Scatter plot  
**Axes:**
- x-axis = annual spend
- y-axis = price dispersion or price variance
- bubble size = number of suppliers or transaction count

**Why it is useful:**
- Helps users identify the categories that combine **high spend** and **high price variation**
- Good first filter for where negotiation effort may generate value
- More useful than just a ranked list because it shows structural differences across categories

---

### D. Top opportunity tables
**Visual:** Ranked tables  
**Examples:**
- Top suppliers by modeled opportunity
- Top categories by modeled opportunity
- Top items with largest benchmark gap

**Why it is useful:**
- Gives buyers a practical starting point
- Easy to scan and filter
- Essential for a V1 dashboard even if more advanced visuals are present

---

# 2. Category / Item Price Diagnostics

This page should help users understand where price variation exists within categories, materials, SKUs, or service lines.

This is where more statistical visuals can add real value.

## Key visuals

### A. Boxplots for comparable items
**Visual:** Boxplot by item, material group, plant, or supplier  
**Shows:** Price distribution for comparable purchases

**Why it is useful:**
- Shows median price, quartiles, and outliers
- Helps identify who is paying above the internal range for a similar item
- More robust than relying on average price alone
- Very good for standardized materials, packaging, MRO, logistics lanes, and similar purchases

**Why this should be in V1:**
This is one of the best non-obvious procurement visuals. It is statistically useful but still easy to explain.

---

### B. Price distribution histogram
**Visual:** Histogram  
**Shows:** Frequency distribution of normalized unit prices for a selected item or item group

**Why it is useful:**
- Helps users see whether the “best price” is a repeatable benchmark or just a one-off outlier
- Gives context before extrapolating savings opportunities
- Useful when there are enough transactions for a selected item or material cluster

---

### C. Price-volume scatter plot
**Visual:** Scatter plot  
**Axes:**
- x-axis = quantity / annual volume
- y-axis = unit price
- color = supplier
- bubble size = spend

**Why it is useful:**
- Shows whether larger volumes are actually getting better prices
- Helps identify cases where a high-volume plant is paying more than a lower-volume plant
- Supports negotiation and aggregation discussions

**Typical insight:**
“We are buying more, but not receiving scale advantage.”

---

### D. Best-price extrapolation chart
**Visual:** Scenario bar / range chart  
**Shows:**
- current weighted average price
- median internal price
- best internal observed price
- price range
- estimated opportunity under different scenarios

**Why it is useful:**
- Makes opportunity sizing more practical and defensible
- Avoids overreliance on a single “best observed price” number
- Helps frame conservative, base-case, and stretch negotiation views

**Recommended scenarios:**
- Conservative: move to median internal price
- Base case: move to best repeatable internal price
- Stretch: move toward best observed benchmark if evidence supports it

---

### E. Time-series price trend
**Visual:** Line chart  
**Shows:** Price trend over time by supplier, item, or category

**Why it is useful:**
- Helps users determine whether price gaps are persistent or recent
- Supports challenge of supplier-led increases
- Useful in categories influenced by market movements

This can become even more powerful later if external indices are added, but V1 can still deliver value using internal trend views alone.

---

# 3. Supplier Negotiation View

This page should group opportunities by supplier so a buyer can prepare for a negotiation conversation.

The purpose is not yet to trigger workflows, but to provide a clear fact base.

## Key visuals

### A. Supplier spend profile
**Visual:** Stacked bar chart or treemap  
**Shows:** Spend by category, business unit, plant, or item group for a selected supplier

**Why it is useful:**
- Gives context on the supplier relationship
- Shows where the spend base sits
- Helps define the negotiation perimeter

---

### B. Internal benchmark ladder / dumbbell chart
**Visual:** Dumbbell chart  
**Shows for selected items:**
- current supplier price
- best internal price
- median internal price

**Why it is useful:**
- Extremely intuitive for procurement users
- Highlights specific negotiation gaps clearly
- Works well when grouped by item or material family

This is one of the strongest visuals for supplier discussions.

---

### C. Supplier opportunity table
**Visual:** Detailed ranked table  
**Recommended columns:**
- item / material
- normalized unit of measure
- annual volume
- annual spend
- current average price
- median internal price
- best internal price
- benchmark gap %
- modeled opportunity value

**Why it is useful:**
- Converts analysis into a practical negotiation fact base
- Lets buyers sort by value, price gap, or material
- Arguably the most important operational view in the dashboard

---

### D. Supplier price dispersion view
**Visual:** Boxplot or beeswarm plot by item  
**Shows:** How the supplier’s pricing compares with peers or internal distributions

**Why it is useful:**
- Helps determine whether the supplier is broadly uncompetitive or only expensive on certain items
- Supports targeted negotiation preparation

---

### E. Supplier item opportunity grouping
**Visual:** Grouped table or bar chart by supplier  
**Shows:** Total opportunity grouped into clusters such as:
- price harmonisation opportunity
- best-price extrapolation opportunity
- volume leverage opportunity

**Why it is useful:**
- Helps frame a more coherent negotiation discussion
- Gives users a clear supplier-level summary without needing workflow logic in V1

---

# 4. Working Capital & Payment Terms View

A good procurement dashboard should not stop at purchase price. Working capital opportunities often provide a second source of value.

## Key visuals

### A. Payment terms distribution
**Visual:** Boxplot or histogram  
**Shows:** Distribution of payment terms across suppliers, categories, or business units

**Why it is useful:**
- Reveals inconsistency in negotiated terms
- Helps identify where suppliers sit outside internal norms
- Good for term harmonisation discussions

---

### B. Spend vs payment term scatter
**Visual:** Scatter plot  
**Axes:**
- x-axis = annual spend
- y-axis = payment terms (days)
- bubble size = supplier criticality or supplier count

**Why it is useful:**
- Identifies large suppliers on weak payment terms
- Helps prioritise working capital negotiations

---

### C. Payment term benchmark table
**Visual:** Ranked table  
**Shows:**
- supplier
- current payment terms
- category median terms
- internal target terms
- estimated working capital benefit

**Why it is useful:**
- Practical and easy to act on
- Helps users identify the clearest opportunities without complex modeling

---

# Most valuable non-obvious visuals for V1

If the goal is to go beyond basic spend charts, the most valuable advanced visuals for V1 are:

## 1. Boxplots
These are highly useful for showing internal price variation and highlighting where a buyer is paying above the normal range for a comparable item.

## 2. Price-volume scatter plots
These are excellent for testing whether procurement is actually getting the expected scale benefit.

## 3. Best-price extrapolation scenario charts
These are useful for showing a range of opportunity outcomes rather than a single savings number.

## 4. Histograms of normalized prices
These help users understand whether benchmark prices are robust or just outliers.

## 5. Dumbbell charts for supplier price comparison
These are particularly good for negotiation preparation because they clearly compare current vs better internal price points.

---

# Suggested opportunity logic for V1

Even if the dashboard is visual-first, the underlying logic should include a few clear opportunity tests.

## 1. Best-price extrapolation
For comparable items, calculate the gap between:
- current price
- median internal price
- best internal observed price

Then estimate potential value based on annual volume.

---

## 2. Price dispersion opportunity
Identify items or categories where internal price spread is unusually large.

This often signals:
- fragmented sourcing
- weak governance
- inconsistent local negotiation
- poor contract adherence

---

## 3. Supplier negotiation opportunity
Group modeled opportunities by supplier where the same supplier appears overpriced on multiple comparable items.

This helps support supplier-level negotiation planning.

---

## 4. Payment term opportunity
Highlight suppliers whose payment terms are weaker than:
- category norm
- business unit norm
- internal policy target

---

# Recommended V1 filters

To make the dashboards useful, the user should be able to filter by:
- category
- subcategory
- supplier
- business unit
- plant / site
- geography
- material / SKU / item group
- time period
- currency

Optional if available:
- incoterm
- contract status
- buyer / owner

---

# Key data fields needed for V1

At minimum, the dashboard should ideally have access to:
- supplier name
- parent supplier / normalized supplier name
- category / subcategory
- material / SKU / item description
- quantity
- unit of measure
- unit price
- total spend
- currency
- transaction date
- plant / business unit / geography
- payment terms

Helpful additional fields:
- contract reference
- incoterm
- pack size / product specification fields
- manufacturer / brand
- price validity period

---

# Recommended V1 output structure

If I were scoping the first release, I would focus on these **must-have views**:

## Page 1: Executive Overview
- Spend concentration chart
- Category x BU heatmap
- Opportunity prioritisation scatter
- Top opportunity tables

## Page 2: Category / Item Diagnostics
- Boxplots for comparable items
- Price histogram
- Price-volume scatter
- Best-price extrapolation scenario chart
- Price trend over time

## Page 3: Supplier Negotiation View
- Supplier spend profile
- Dumbbell chart for benchmark gaps
- Supplier opportunity table
- Supplier price dispersion view

## Page 4: Working Capital View
- Payment terms distribution
- Spend vs payment term scatter
- Payment term benchmark table

---

# Final recommendation

For a procurement spend cube V1, the priority should be to combine:
- **clear spend transparency**
- **robust price variance diagnostics**
- **supplier-level negotiation fact bases**
- **simple working capital opportunity identification**

If the team wants to go beyond standard waterfall charts, the best place to start is with:

1. **Boxplots** for comparable item price distributions  
2. **Price-volume scatter plots**  
3. **Best-price extrapolation scenario charts**  
4. **Histograms of normalized prices**  
5. **Dumbbell charts for supplier negotiation gaps**  

These visuals are advanced enough to add real analytical value, but still practical and explainable for a V1 product.
