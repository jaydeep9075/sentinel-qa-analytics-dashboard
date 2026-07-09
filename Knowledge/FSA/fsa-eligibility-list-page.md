# FSA Eligibility List Page

## Purpose

This page serves as an eligibility reference for products and services that may qualify under FSA, HSA, or HRA rules.

## Page Summary

- URL: https://fsa.devhec.com/fsa-eligibility-list
- Page type: Eligibility reference and search page
- Primary goal: help users understand what is eligible, browse categories of eligible items, and navigate to relevant product pages.

## Main Page Structure

1. Shared site header and navigation
2. Hero section introducing the eligibility list
3. Search and filtering controls
4. Alphabetic or category-based browsing
5. Eligibility cards or list items
6. Related educational or promotional content
7. Shared footer

## Key Content Areas

- The page is informational and reference-driven.
- Users can search for an item, browse by letter, and review eligibility status.
- Each entry should communicate whether an item is eligible, not eligible, or conditionally eligible.

## Agent and LLM Notes

Treat this page as a structured knowledge and discovery page for healthcare spending eligibility. It should be understood as a decision-support resource, not a standard product listing page.

## Related Knowledge

- Shared navigation: [navigation-menu.md](navigation-menu.md)
- Shared footer: [footer.md](footer.md)

| Element    | Content     | Action                                  |
| ---------- | ----------- | --------------------------------------- |
| **Button** | `Load More` | AJAX load more items for current letter |

```javascript
data-el-ajax-url="/on/demandware.store/Sites-FSASTORE-Site/default/Elist-ShowAjax?cgid=el-a&page=2"
```

#### Recommended Locators

```playwright
// Cards
page.locator('.c-elist__card__heading__title:has-text("Acetaminophen")')
page.locator('.c-elist__card__heading__type.eligible')

// SHOP links
page.locator('.js-shop-link:has-text("SHOP")')

// View Details
page.locator('.c-elist__card__action__link__label:has-text("View Full Details")')

// Collapse/Expand
page.locator('.c-elist__card__header')
page.locator('.c-elist__card__collapse')

// Load More
page.locator('.js-el-load-more:has-text("Load More")')
```

---

## Section 5: Popular Categories (Zmags/FASTR)

**Block:** `Popular Categories` (Zmags/FASTR Interactive Experience)

### 5.1 Category Icons

| Icon                  | Category              | URL                                    |
| --------------------- | --------------------- | -------------------------------------- |
| New Arrivals          | New Arrivals          | `/new-arrivals`                        |
| Best Sellers          | Best Sellers          | `/best-sellers`                        |
| Acne & Skincare       | Acne & Skincare       | `/personal-care/acne-and-skincare`     |
| Pain Relief           | Pain Relief           | `/medicine-and-treatments/pain-relief` |
| Suncare               | Suncare               | `/personal-care/suncare`               |
| Menstrual Care        | Menstrual Care        | `/personal-care/menstrual-care`        |
| Bundles               | Bundles               | `/bundles`                             |
| Surprisingly Eligible | Surprisingly Eligible | `/surprisingly-eligible`               |

### 5.2 Interactive Experience

The Popular Categories section uses **Zmags/FASTR** interactive content:

| Technology | Purpose                              |
| ---------- | ------------------------------------ |
| Zmags      | Interactive catalog/experience       |
| FASTR      | Content rendering                    |
| SVG        | Vector graphics with clickable areas |

### 5.3 Clickable Areas (Hotspots)

Each category icon is wrapped in a clickable `<a>` tag with `href` pointing to the category URL.

#### Recommended Locators

```playwright
// Popular categories (via FASTR)
page.locator('.fastr-container a[href="/new-arrivals"]')
page.locator('.fastr-container a[href="/best-sellers"]')
page.locator('.fastr-container a[href="/personal-care/acne-and-skincare"]')
page.locator('.fastr-container a[href="/medicine-and-treatments/pain-relief"]')
page.locator('.fastr-container a[href="/personal-care/suncare"]')
page.locator('.fastr-container a[href="/personal-care/menstrual-care"]')
page.locator('.fastr-container a[href="/bundles"]')
page.locator('.fastr-container a[href="/surprisingly-eligible"]')
```

---

## Section 6: Top Reads Articles

**Block:** `c-article` carousel

### 6.1 Article Cards

| #   | Article Title                                                 | URL                                                                    |
| --- | ------------------------------------------------------------- | ---------------------------------------------------------------------- |
| 1   | **How to Budget and Plan Around Your FSA Rollover**           | `/learn-fsa-rollover.html`                                             |
| 2   | **10 Eligible Purchases to Improve Work From Home**           | `/learn-fsa-eligible-work-from-home-wellness.html`                     |
| 3   | **2026 FSA Contributions Limits are Here!**                   | `/learn-new-fsa-contribution-limits.html`                              |
| 4   | **Can I have an FSA and an HSA? Exploring FSA compatibility** | `/articles/learn-can-i-have-an-fsa-and-hsa-options-for-fsa-users.html` |

### 6.2 Article Card Structure

```
.c-article__card
  ├── .c-article__card__header
  │   └── .c-article__card__media (image)
  ├── .c-article__card__body
  │   ├── .c-article__card__title (linked)
  │   └── .c-article__card__description
  └── .c-article__card__footer
      └── .c-article__card__link (Learn More/Get Started)
```

### 6.3 Carousel Controls

| Element       | Description      |
| ------------- | ---------------- |
| `.slick-prev` | Previous slide   |
| `.slick-next` | Next slide       |
| `.slick-dots` | Slide indicators |

#### Recommended Locators

```playwright
// Article carousel
page.locator('.c-article__card__title:has-text("How to Budget and Plan Around Your FSA Rollover")')
page.locator('.c-article__card__link:has-text("Learn More")')

// Carousel controls
page.locator('.slick-prev')
page.locator('.slick-next')
```

---

## Section 7: Telehealth Banner (FASTR)

**Block:** Telehealth Services Banner (FASTR Interactive)

### 7.1 Banner Content

| Element        | Content                                         |
| -------------- | ----------------------------------------------- |
| **Heading**    | `Telehealth services for all your health needs` |
| **CTA**        | `Learn More` → `/telehealth.html`               |
| **Navigation** | Previous/Next arrows for carousel               |

### 7.2 Telehealth Cards (Carousel)

| Card           | Category       | URL                   |
| -------------- | -------------- | --------------------- |
| Mental Health  | Mental Health  | `/mental-health.html` |
| Women's Health | Women's Health | `/womens-health.html` |
| Insoles        | Insoles        | `/bilt-labs.html`     |
| Weight Loss    | Weight Loss    | `/weight-loss.html`   |
| Lab Testing    | Lab Testing    | `/health-labs.html`   |
| Men's Health   | Men's Health   | `/rexmd.html`         |
| Dental Care    | Dental Care    | `/dental-care.html`   |

### 7.3 Card Structure (FASTR)

```
.fastr-container
  └── .fastr-shape-anchor (each card)
      ├── rx="12" ry="12" (rounded rectangle)
      ├── text element (category name)
      └── icon/path (category icon)
```

#### Recommended Locators

```playwright
// Telehealth banner
page.locator('.fastr-container a[href="/mental-health.html"]')
page.locator('.fastr-container a[href="/womens-health.html"]')
page.locator('.fastr-container a[href="/weight-loss.html"]')
page.locator('.fastr-container a[href="/health-labs.html"]')
page.locator('.fastr-container a[href="/rexmd.html"]')
page.locator('.fastr-container a[href="/dental-care.html"]')

// CTA
page.locator('.fastr-container a[href="/telehealth.html"]:has-text("Learn More")')
```

---

## Section 8: Email Signup

**Block:** `home-email-signup`

| Element        | Content                                                                                                                     |
| -------------- | --------------------------------------------------------------------------------------------------------------------------- |
| **Headline**   | Get $20 off your first $150 order                                                                                           |
| **Subtext**    | Sign up for discounts, special promotions, tips, and more!                                                                  |
| **Input**      | Email field with label "Enter Email Address"                                                                                |
| **Button**     | "Sign Up"                                                                                                                   |
| **Disclaimer** | By entering your email address, you agree to our Terms of Use and Privacy Notice, including Notice of Financial Incentives. |

#### Recommended Locators

```playwright
// Email signup
page.locator('#hpEmailSignUp')
page.locator('.js-subscribeEmail:has-text("Sign Up")')
```

---

## Section 9: Site Footer

### 9.1 Footer Columns

| Column               | Links                                                                                              |
| -------------------- | -------------------------------------------------------------------------------------------------- |
| **Customer Service** | FAQ, Contact Us, Shipping & Returns, FSA Eligible Guarantee                                        |
| **Resources**        | Savings Center, Learning Center, Eligibility List, FSA Advocacy, What is an FSA?                   |
| **Our Company**      | About Us, Awards & Press, Careers, Become a Partner                                                |
| **My Account**       | Manage My Account, Order Status, About FSA Perks, FSA Perks Dashboard, Sign Up for Deadline Alerts |

### 9.2 Help Section

| Action             | URL / Behavior                                                    |
| ------------------ | ----------------------------------------------------------------- |
| **Call**           | `tel:18883721450` (1-888-372-1450)                                |
| **FAQ**            | `https://help.fsastore.com/hc/en-us/categories/115000977647-FAQs` |
| **Contact Us**     | `/about-fsa-store-contactus.html`                                 |
| **Live Chat**      | `javascript:$zopim.livechat.window.show();`                       |
| **Shop HSA Store** | `http://hsastore.com`                                             |

### 9.3 Footer Features

| Feature           | Content                                                                                                                      |
| ----------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| **Trust Badges**  | 100% Eligibility Guarantee, HiTrust, BBB, LegitScript                                                                        |
| **Payment Icons** | Mastercard, Visa, Amex, Discover                                                                                             |
| **Social Links**  | LinkedIn, Facebook, Twitter/X, Instagram                                                                                     |
| **Legal**         | Terms of Use, Privacy Notice, California Privacy Notice, Consumer Health Data Notice, Accessibility, Accessibility Statement |
| **TrustArc**      | Consent management (TrustArc)                                                                                                |

---

## Complete URL Map

### Eligibility List Pages

```
/fsa-eligibility-list                    → Main Eligibility List (A section default)
/fsa-eligibility-list/a                  → A section
/fsa-eligibility-list/b                  → B section
/fsa-eligibility-list/c                  → C section
... (A-Z)
/fsa-eligibility-list/z                  → Z section
```

### Detail Pages

```
/fsa-eligibility-list/a/aa-meeting-transportation
/fsa-eligibility-list/a/abdominoplasty
/fsa-eligibility-list/a/acetaminophen
... (full detail for each item)
```

### API/Endpoints

```
/on/demandware.store/Sites-FSASTORE-Site/default/Elist-ShowAjax?cgid=el-a
/on/demandware.store/Sites-FSASTORE-Site/default/Elist-ShowAjax?cgid=el-a&page=2
```

---

## Page Metadata

```javascript
{
  "title": "FSA Eligibility List | Find & Buy FSA Eligible Items - FSA Store | FSA Store | Salesforce Commerce Cloud | 6.1.0",
  "description": "FSA Store is your one-stop-shop to find and buy Flexible Spending Account eligible items. Browse our full list of FSA eligible items from FSA Store here!",
  "keywords": "FSA Store",
  "pageType": "Eligibility List Page",
  "platform": "Salesforce Commerce Cloud (SFCC)",
  "categoryId": "fsa-eligibility-list",
  "template": "categoryList",
  "canonical": "https://fsa.devhec.com/fsa-eligibility-list",
  "og:title": "FSA Eligibility List | Find & Buy FSA Eligible Items - FSA Store | FSA Store",
  "og:type": "Site",
  "og:image": "/on/demandware.static/Sites-FSASTORE-Site/-/default/dw28867c13/images/Share-logo.jpg"
}
```

### Analytics Data

```javascript
{
  "ecomm_pagetype": "Eligibility List Page",
  "ecomm_category": "FSA Eligibility List",
  "department": "FSA Eligibility List",
  "collection_title": "FSA Eligibility List",
  "collection_url": "https://fsa.devhec.com/fsa-eligibility-list"
}
```

---

## Key Interactions

### 1. Account Type Selection

```
Click dropdown → Select account type → Filter list
```

### 2. Alphabet Navigation

```
Click letter → AJAX load → Update list
```

### 3. Search/Filter

```
Type in search → Filter results → Show matching items
```

### 4. Card Expand

```
Click card header → Expand details → Click View Full Details → Navigate to detail page
```

### 5. Shop Link

```
Click SHOP → Navigate to category/product listing
```

### 6. Load More

```
Click Load More → AJAX load more items → Append to list
```

---

## Locator Reference (Playwright Selectors)

### Recommended Selectors

| Element                | Preferred Selector                                                  | Fallback                      |
| ---------------------- | ------------------------------------------------------------------- | ----------------------------- |
| Hero Heading           | `h1:has-text("The Complete FSA Eligibility List®")`                 | `.c-elist__header__text h1`   |
| Shop Eligible Products | `.btn-primary:has-text("Shop Eligible Products")`                   | `.eslist-header-btn`          |
| Account Type Selector  | `.js-elist-dropdownToggle`                                          | `.js-list-at`                 |
| Search Input           | `.js-el-filter-txt`                                                 | `input[name="searchTerm"]`    |
| Alphabet Nav (Active)  | `.c-elist__listNavigation__btn.active`                              | `.js-get-elists.active`       |
| Alphabet Nav (Letter)  | `.c-elist__listNavigation__btn:has-text("A")`                       | `.js-get-elists.item-A`       |
| Eligibility Card       | `.c-elist__card__heading__title:has-text("Acetaminophen")`          | `.c-elist__card`              |
| Eligibility Badge      | `.c-elist__card__heading__type.eligible`                            | -                             |
| SHOP Link              | `.js-shop-link:has-text("SHOP")`                                    | -                             |
| View Details           | `.c-elist__card__action__link__label:has-text("View Full Details")` | -                             |
| Load More              | `.js-el-load-more:has-text("Load More")`                            | -                             |
| Filter Panel           | `.js-elist-listFilters-btn`                                         | -                             |
| Eligibility Checkbox   | `#input-eligible`                                                   | -                             |
| LMN Checkbox           | `#input-lmn`                                                        | -                             |
| Article Card           | `.c-article__card__title:has-text("How to Budget")`                 | -                             |
| Carousel Controls      | `.slick-prev`, `.slick-next`                                        | -                             |
| Email Signup           | `#hpEmailSignUp`                                                    | `input[name="hpEmailSignUp"]` |
| Footer                 | `#footercontent`                                                    | `footer`                      |

### Filter Panel Locators

```playwright
// Open filter panel
page.locator('.js-elist-listFilters-btn')

// Eligibility filters
page.locator('#input-eligible')
page.locator('#input-lmn')
page.locator('#input-rx')
page.locator('#input-not-eligible')

// Expense type filters
page.locator('#expense-type-products')
page.locator('#expense-type-services')

// Done button
page.locator('.js-eListfilter-done')
```

---

## Complete Page Flow for Test Automation

```
1. Navigate to /fsa-eligibility-list
2. Verify hero heading "The Complete FSA Eligibility List®"
3. Click "Shop Eligible Products" → Verify navigation to /best-sellers
4. Return to eligibility list
5. Click account type dropdown → Select "HSA" → Verify list updates
6. Select "FSA" again → Verify list updates
7. Type "acetaminophen" in search → Verify filtered results
8. Clear search → Verify all results visible
9. Click "A" alphabet navigation → Verify A section active
10. Click an eligibility card header → Expand → Verify description visible
11. Click "View Full Details" → Verify navigation to detail page
12. Return to eligibility list
13. Click "SHOP" link on an item → Verify navigation to category
14. Return to eligibility list
15. Click "B" alphabet navigation → Verify B section loaded
16. Click "Load More" → Verify more items loaded
17. Scroll to Popular Categories → Click a category → Verify navigation
18. Scroll to Top Reads → Click article → Verify navigation
19. Scroll to Telehealth Banner → Click a telehealth card → Verify navigation
20. Scroll to Email Signup → Enter email → Submit → Verify success
```

---

## Content Types (SFCC)

### Content Assets Referenced

| Content ID                   | Purpose                               |
| ---------------------------- | ------------------------------------- |
| `ed1b509d187464d82c614c94fb` | Eligibility List Header               |
| `438c2a54a1d1824ffc73de3a69` | Popular Categories (with Zmags/FASTR) |
| `9565718e22b053f23f6c8f1477` | Top Reads Articles                    |

### Category IDs (Eligibility List)

| Category ID | Letter |
| ----------- | ------ |
| `el-a`      | A      |
| `el-b`      | B      |
| `el-c`      | C      |
| ...         | ...    |
| `el-z`      | Z      |
