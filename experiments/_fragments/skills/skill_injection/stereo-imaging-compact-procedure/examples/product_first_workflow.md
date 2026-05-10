# Product-First Workflow

This example is synthetic. It shows the planning shape, not a case-specific answer.

## 1. Start With Candidate Singles

Create a working table of observation candidates:

| id | target | satellite | midpoint | access margin | steering | note |
|---|---|---|---|---|---|---|
| A | T01 | S1 | mid-window | large | modest left | near nadir |
| B | T01 | S2 | nearby | large | modest right | different view |
| C | T01 | S1 | same pass | medium | forward | backup |
| D | T02 | S3 | mid-window | large | modest | first view |

Keep candidates comfortably inside access windows. If you do not know the exact edge, choose shorter observations near the middle of likely access.

## 2. Build Products Per Target

Group same-target candidates before adding them to the schedule:

| product | observations | reason to try | risk |
|---|---|---|---|
| P1 | A + B | cross-satellite pair with viewpoint diversity | pixel-scale mismatch |
| P2 | A + C | same-satellite same-pass backup | slew gap in one timeline |
| P3 | A + B + C | tri-stereo upgrade with near-nadir anchor | more timeline conflicts |

Rank products by whether they cover a new target, then by likely quality. Prefer products with margin over products that barely touch thresholds.

## 3. Insert As A Unit

For each product:

1. Copy the current per-satellite timelines.
2. Insert every observation in the product into its satellite timeline.
3. Sort each affected timeline by start time.
4. Check only nearby same-satellite neighbors for overlap and transition gaps.
5. Keep the product only if all its observations fit.

If one observation fails, discard or retime the whole product. Do not leave a single image behind unless it still supports another valid product.

## 4. Repair By Product Value

When two products compete for the same satellite time:

| keep | remove | why |
|---|---|---|
| product covering an uncovered target | duplicate upgrade on an already-covered target | coverage improves normalized score more reliably |
| product with a near-nadir tri anchor | marginal pair near thresholds | more robust validation |
| product blocking few future options | product blocking many candidates | preserves schedule flexibility |

After repair, validate the full `solution.json`. If it is valid but scores zero, look at product formation: add or retime same-target pairs/triples rather than adding more unrelated single observations.
