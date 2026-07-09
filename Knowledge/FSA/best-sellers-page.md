# Best Sellers Page

## Purpose

This is the product discovery landing page for top-selling FSA-eligible items.

## Page Summary

- URL: https://fsa.devhec.com/best-sellers
- Page type: Category landing page
- Primary goal: help shoppers discover popular products, narrow results by budget, and move toward product detail or cart actions.

## Main Page Structure

1. Shared site header and navigation
2. Breadcrumb trail
3. Page title and introductory content
4. Price-based product filters
5. Product grid with cards
6. Pagination or load more behavior
7. Supporting SEO/content section
8. Shared footer

## Key Content Areas

- Product cards typically include product name, price, rating, and a clear add-to-cart action.
- Filters help users refine the result set by price range.
- The page serves as a curated discovery surface rather than a standalone informational page.

## Agent and LLM Notes

Use this page as the canonical reference for best-seller product browsing behavior. Keep the focus on user intent, content hierarchy, and product discovery flow.

## Related Knowledge

- Shared navigation: [navigation-menu.md](navigation-menu.md)
- Shared footer: [footer.md](footer.md)

### 3. Load More Products

```
Click "Load More" → AJAX request → Append next page of products to grid
```

### 4. View All Products

```
Click "View All" → Navigate to `/best-sellers?page=all` → Load full product list
```

### 5. Product Quick View

```
Hover over product tile → "QUICK VIEW" button appears → Click to open modal
```

---

## Locator Reference (Playwright Selectors)

### Recommended Selectors

| Element              | Preferred Selector                              | Fallback                                     |
| -------------------- | ----------------------------------------------- | -------------------------------------------- |
| Logo                 | `img[alt="FSA Store"]`                          | `[data-testid="logo"]`                       |
| Search Input         | `input[placeholder="Search Eligible Products"]` | `[data-cnstrc-search-input]`                 |
| Sign In              | `button[aria-label="Sign in"]`                  | `[data-testid="account-popover-trigger"]`    |
| Cart                 | `a[aria-label="Open cart"]`                     | `[data-testid="minicart-trigger"]`           |
| Menu                 | `button[aria-label="Open navigation menu"]`     | `button[aria-haspopup="dialog"]`             |
| Breadcrumb Home      | `a:has-text("Home")`                            | `nav[aria-label="breadcrumb"] a:first-child` |
| Filter Chips         | `[data-testid="category-filters-link"]`         | `button:has-text("Under $")`                 |
| Product Tile Root    | `[data-testid="product-tile-root-{id}"]`        | `[data-view-item-id="{id}"]`                 |
| Load More Button     | `button:has-text("Load More")`                  | `[data-testid="load-more"]`                  |
| View All Link        | `a:has-text("View All")`                        | `a[href*="page=all"]`                        |
| SEO Read More Button | `[data-testid="seo-copy-expand-button"]`        | `button:has-text("Read more")`               |
| Footer               | `#footercontent`                                | `footer`                                     |

---

## Page Models (Data Structures)

### Product Tile Data Model

```javascript
{
  "id": "42298",
  "name": "Dr. Scholl's Odor-X Athlete's Foot 24-hour Medicated AF Spray Powder, 4.7 oz.",
  "brand": "Dr. Scholl's",
  "price": "$303.30",
  "isNew": true,
  "isBestSeller": true,
  "rating": 4.0,
  "reviewsCount": 76,
  "imageUrl": "https://fsa.devhec.com/dw/image/...",
  "productUrl": "/dr-scholl-s-odor-x-athlete-s-foot-24-hour-medicated-af-spray-powder-4-7-oz/42298.html"
}
```

### Category Filter Data Model

```javascript
{
  "label": "Under $25",
  "url": "/best-sellers?pmax=25.00&pmin=0.00",
  "isActive": false
}
```

---

## Analytics & Tracking

| Platform           | ID/Key                               |
| ------------------ | ------------------------------------ |
| Google Tag Manager | `GTM-K4TL22P`                        |
| Constructor.io     | `key_kWFGqMuw8gvfhv87`               |
| Bloomreach         | `https://analytics-api.fsastore.com` |

---

## Knowledge Graph Summary

```
FSA Store Best Sellers Page
├── Type: E-Commerce Category Landing Page
├── Industry: Healthcare / FSA Products
├── Key Features:
│   ├── Price-based Category Filters
│   ├── Infinite Scroll / Load More Pagination
│   ├── Product Grid with Quick Add to Cart
│   ├── Inline Promotional Content
│   └── SEO-Optimized Description
├── Target Audience:
│   ├── FSA/HSA Account Holders Looking for Popular Items
│   └── Health-Conscious Consumers
└── Primary CTAs:
    ├── Add to Cart
    ├── Quick View
    ├── Filter Products by Price
    └── Load More / View All Products
```
