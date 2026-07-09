# Home Page

## Purpose

This is the main landing page for the FSA Store and the primary entry point for product discovery, category exploration, and promotional content.

## Page Summary

- URL: https://fsa.devhec.com/
- Page type: Homepage
- Primary goal: introduce the site, guide users to key categories, and direct them toward products, eligibility information, or account-related actions.

## Main Page Structure

1. Shared site header and navigation
2. Promotional banner or alert area
3. Category navigation and discovery blocks
4. Hero and featured content sections
5. Product or topic collection sections
6. Email signup or support content
7. Shared footer

## Key Content Areas

- The homepage is a hub for category exploration and marketing content.
- It connects users to shopping paths such as best sellers, eligibility information, educational content, and account access.
- The page should be interpreted as the central starting point for the FSA Store experience.

## Agent and LLM Notes

Use this page as the primary entry point for site understanding. It should be linked to product discovery, education, and account-related journeys.

## Related Knowledge

- Shared navigation: [navigation-menu.md](navigation-menu.md)
- Shared footer: [footer.md](footer.md)

#### UI Elements

| Element           | Locator                                                                        | Action      |
| ----------------- | ------------------------------------------------------------------------------ | ----------- |
| **Headline**      | `h2` text: "Get $20 off your first $150 order"                                 | Display     |
| **Subtext**       | Text: "Sign up for discounts, special promotions, tips, and more!"             | Display     |
| **Email Input**   | `input[type="email"]` with placeholder "enter email address"                   | Input       |
| **Submit Button** | `button[type="submit"]` text: "Sign Up"                                        | Submit Form |
| **Disclaimer**    | Small text: "By entering your email address, you agree to our Terms of Use..." | Display     |

#### Flow

```
Email Input → Validate → Submit → POST /resources/email-signup → Confirmation
```

---

### 4.6 Featured Picks (The season's brightest picks)

**Block:** `Featured 3-Up` (`builder-d5f66ce5d94849d380b3ad6c63de0ca8`)

#### Featured Tiles

| Tile  | Image           | Title                      | Destination              |
| ----- | --------------- | -------------------------- | ------------------------ |
| **1** | Lifestyle image | **Surprisingly Eligible™** | `/surprisingly-eligible` |
| **2** | Lifestyle image | **Trending**               | `/fsa-trending`          |
| **3** | Lifestyle image | **Best Sellers**           | `/best-sellers`          |

#### ARIA Tree

```
heading "The season's brightest picks"
├── link "Surprisingly Eligible™" → /surprisingly-eligible
│   └── image + arrow icon
├── link "Trending" → /fsa-trending
│   └── image + arrow icon
└── link "Best Sellers" → /best-sellers
    └── image + arrow icon
```

---

### 4.7 Value Propositions

**Block:** `What Sets Us Apart` (`builder-51f0e7f69c0e40f3ba6e0f2a0996c752`)

#### Value Props

| #   | Icon      | Title                                  | Description                                | Link                     |
| --- | --------- | -------------------------------------- | ------------------------------------------ | ------------------------ |
| 1   | Checkmark | **100% Product Eligibility Guarantee** | Guaranteed FSA eligibility on all products | `/surprisingly-eligible` |
| 2   | Truck     | **Free Shipping on $50+**              | Free shipping on orders over $50           | `/best-sellers`          |
| 3   | Rewards   | **FSA Perks® Points**                  | Earn points, unlock member-only rewards    | `/loyalty-perks`         |
| 4   | List      | **Complete FSA Eligibility List®**     | Full FSA eligibility database              | `/fsa-eligibility-list`  |

#### ARIA Tree

```
heading "More value. More confidence. More from your FSA."
├── link
│   ├── icon: 100% Eligibility Guarantee
│   ├── text "100% Product Eligibility Guarantee"
│   └── → /surprisingly-eligible
├── link
│   ├── icon: Free Shipping
│   ├── text "Free Shipping on $50+"
│   └── → /best-sellers
├── link
│   ├── icon: FSA Perks
│   ├── text "FSA Perks® Points"
│   └── → /loyalty-perks
└── link
    ├── icon: Eligibility List
    ├── text "Complete FSA Eligibility List®"
    └── → /fsa-eligibility-list
```

---

### 4.8 Brands We Love

**Block:** `Brands We Love` (`builder-c8ac2ae9c4324c139a56c751a8dac02c`)

#### Brand Logos

| Row   | Brand          | Logo                | URL                     |
| ----- | -------------- | ------------------- | ----------------------- |
| **1** | Supergoop!     | Supergoop logo      | `/brand/supergoop`      |
| **1** | Chirp          | Chirp logo          | `/brand/chirp`          |
| **1** | La Roche-Posay | La Roche-Posay logo | `/brand/la-roche-posay` |
| **2** | Neutrogena     | Neutrogena logo     | `/brand/neutrogena`     |
| **2** | EltaMD         | EltaMD logo         | `/brand/eltamd`         |
| **2** | Cure Inc.      | Cure Inc. logo      | `/brand/cure-inc.`      |

> **Note:** Brands are displayed in two rows of three.

#### ARIA Tree

```
heading "Brands you love"
├── grid (2 columns on mobile)
│   ├── link (Supergoop!) → /brand/supergoop
│   ├── link (Chirp) → /brand/chirp
│   ├── link (La Roche-Posay) → /brand/la-roche-posay
│   ├── link (Neutrogena) → /brand/neutrogena
│   ├── link (EltaMD) → /brand/eltamd
│   └── link (Cure Inc.) → /brand/cure-inc.
└── button "Shop All Brands" → /shop-all-brands-a-z.html
```

---

### 4.9 Wellness Carousel

**Block:** `sow-3-panel-test` (`builder-3d94a656aebb49b38c4579c4d81daa3a`)

#### Wellness Panels

| Panel      | Brand/Image       | Headline                                  | Description               | Badge           | Destination                     |
| ---------- | ----------------- | ----------------------------------------- | ------------------------- | --------------- | ------------------------------- |
| **Main**   | FSA Store Optical | "Discover the latest Meta AI glasses."    | FSA eligible eyewear      | "FSA eligible"  | `https://contacts.fsastore.com` |
| **Second** | REXMD             | "ED medication made simple."              | Men's health telemedicine | "$2 per tablet" | `https://track.rexmd.com/...`   |
| **Third**  | Bilt Labs         | "Custom insoles that support every step." | Orthotic insoles          | "Medical grade" | `https://biltlabs.com/...`      |

#### ARIA Tree

```
heading "Wellness, wherever you are"
├── link (Main Spot) → External
│   ├── image: FSA Store Optical
│   ├── text "Discover the latest Meta AI glasses."
│   ├── badge "FSA eligible"
│   └── arrow icon
├── link (Second Spot) → External
│   ├── image: REXMD
│   ├── text "ED medication made simple."
│   ├── badge "$2 per tablet"
│   └── arrow icon
└── link (Third Spot) → External
    ├── image: Bilt Labs
    ├── text "Custom insoles that support every step."
    ├── badge "Medical grade"
    └── arrow icon
```

---

### 4.10 Caring Mill Block

**Block:** `Caring Mill Block` (`builder-ea794a906034406fb7b010e9de4ba077`)

#### UI Elements

| Element         | Content                                                                                           | Destination                                    |
| --------------- | ------------------------------------------------------------------------------------------------- | ---------------------------------------------- |
| **Top Banner**  | "EXCLUSIVELY AT FSA STORE®"                                                                       | N/A                                            |
| **Left Panel**  | Image + "Premium-quality hi-tech health products for less." + Shop Now                            | `/brand/caring-mill?brand=caring-mill-by-aura` |
| **Right Panel** | Image + "Just as effective as top over-the-counter brands, but easier on your wallet." + Shop Now | `/brand/caring-mill`                           |

#### ARIA Tree

```
section "Caring Mill"
├── banner "EXCLUSIVELY AT FSA STORE®"
├── link
│   ├── image: Caring Mill product
│   ├── text "Premium-quality hi-tech health products for less."
│   └── button "Shop Now" → /brand/caring-mill?brand=caring-mill-by-aura
└── link
    ├── image: Caring Mill brand
    ├── text "Just as effective as top over-the-counter brands, but easier on your wallet."
    └── button "Shop Now" → /brand/caring-mill
```

---

## Section 5: Footer

### 5.1 Footer Links

#### Customer Service

| Link                   | URL                                                               |
| ---------------------- | ----------------------------------------------------------------- |
| FAQ                    | `https://help.fsastore.com/hc/en-us/categories/115000977647-FAQs` |
| Contact Us             | `/about-fsa-store-contactus.html`                                 |
| Shipping & Returns     | `/shipping-and-returns.html`                                      |
| FSA Eligible Guarantee | `/fsa-eligible-guarantee-policy.html`                             |

#### Resources

| Link              | URL                              |
| ----------------- | -------------------------------- |
| Savings Center™   | `/savings-center.html`           |
| Learning Center   | `/learning-center.html`          |
| Eligibility List® | `/fsa-eligibility-list`          |
| FSA Advocacy      | `https://www.taxfreebetter.com/` |
| What is an FSA?   | `/what-is-an-fsa.html`           |

#### Our Company

| Link             | URL                                        |
| ---------------- | ------------------------------------------ |
| About Us         | `https://www.health-ecommerce.com/about`   |
| Award & Press    | `https://www.health-ecommerce.com/blog`    |
| Careers          | `https://boards.greenhouse.io/fsastorecom` |
| Become a Partner | `/become-a-partner.html`                   |

#### My Account

| Link                         | URL                    |
| ---------------------------- | ---------------------- |
| Manage My Account            | `/my-account`          |
| Order Status                 | `/orders`              |
| About FSA Perks®             | `/loyalty-perks`       |
| FSA Perks® Dashboard         | `/loyalty-perks`       |
| Sign Up for Deadline Alerts® | `/fsa-deadline-alerts` |

### 5.2 Social Links

| Platform  | Icon           | URL                                                 |
| --------- | -------------- | --------------------------------------------------- |
| LinkedIn  | LinkedIn logo  | `https://www.linkedin.com/company/healthecommerce/` |
| Facebook  | Facebook logo  | `https://www.facebook.com/FSAstore`                 |
| Twitter/X | Twitter/X logo | `https://x.com/FSAstore`                            |
| Instagram | Instagram logo | `https://www.instagram.com/fsastore/`               |

### 5.3 Footer Features

| Feature           | Description                                                                                         |
| ----------------- | --------------------------------------------------------------------------------------------------- |
| **Email Signup**  | Email input + Sign Up button (footer placement)                                                     |
| **Trust Badges**  | 100% Eligibility Guarantee, LegitScript seal                                                        |
| **Payment Icons** | Visa, Mastercard, Amex, Discover                                                                    |
| **Legal Links**   | Terms of Use, Privacy Notice, California Privacy Notice, Consumer Health Data Notice, Accessibility |

### 5.4 Live Chat Button

**Floating Button:** `Chat` with chat icon

| Property | Value                     |
| -------- | ------------------------- |
| Position | Fixed, bottom right       |
| Color    | `#ff295b` (pink)          |
| Action   | Opens Zendesk chat widget |
| Classes  | `live-chat-button`        |

---

## Complete Navigation Flow Map

```
Home Page
│
├── Top Bar
│   ├── FSA Store (Current)
│   └── HSA Store (External)
│
├── Header
│   ├── Logo → Home
│   ├── Search → Search Results
│   ├── Account → Login/My Account
│   └── Cart → /cart
│
├── Health Categories
│   ├── For You → /personalized-picks.html
│   ├── Weight Loss → /patiently/fsa-weight-loss.html
│   ├── Vision → External (Contacts)
│   ├── Oura Ring → External
│   ├── Sleep & CPAP → /sleep-and-cpap.html
│   ├── Dental Care → External (SmileSet)
│   ├── Aligners → /dental-care.html
│   ├── Lab Testing → /health-labs.html
│   ├── Insoles → External (Bilt Labs)
│   └── All Telehealth → /telehealth.html
│
├── Hero Carousel
│   ├── Suncare → /personal-care/suncare
│   ├── Caring Mill → /brand/caring-mill
│   └── Patiently → /patiently/fsa-weight-loss.html
│
├── Shop By Price → Category pages with price filters
├── Shop By Condition → Health condition category pages
├── Shop By Category → Category pages
├── Email Signup → Email subscription
├── Featured Picks → Category pages
├── Value Propositions → Various pages
├── Brands We Love → Brand pages
├── Wellness Carousel → External/Partner pages
└── Caring Mill → Brand pages
```

---

## Key Page Interactions

### 1. Search Flow

```
Input → Autocomplete suggestions → Submit → Search Results
```

### 2. Email Signup Flow

```
Input email → Submit → POST /resources/email-signup → Success/Error
```

### 3. Cart Flow

```
Click cart icon → Open minicart → Proceed to checkout
```

### 4. Account Flow

```
Click Sign In → Open popover → Login/Register → My Account
```

### 5. Chat Flow

```
Click Chat button → Open Zendesk widget → Start chat
```

---

## Locator Reference (Playwright Selectors)

### Recommended Selectors

| Element      | Preferred Selector                              | Fallback                                         |
| ------------ | ----------------------------------------------- | ------------------------------------------------ |
| Logo         | `img[alt="FSA Store"]`                          | `[data-testid="logo"]`                           |
| Search Input | `input[placeholder="Search Eligible Products"]` | `[data-cnstrc-search-input]`                     |
| Sign In      | `button[aria-label="Sign in"]`                  | `[data-testid="account-popover-trigger"]`        |
| Cart         | `a[aria-label="Open cart"]`                     | `[data-testid="minicart-trigger"]`               |
| Menu         | `button[aria-label="Open navigation menu"]`     | `button[aria-haspopup="dialog"]`                 |
| Email Signup | `input[type="email"][name="emailSignup"]`       | `#emailSignup`                                   |
| Live Chat    | `button.live-chat-button`                       | `[data-testid="button-Button"]:has-text("Chat")` |

### Section Selectors

| Section           | Selector                                                       |
| ----------------- | -------------------------------------------------------------- |
| Top Bar           | `.bg-accent` or `[builder-id="builder-ff6a342..."]`            |
| Hero              | `.builder-4f221e9d...` or `[builder-id="builder-4f221e9d..."]` |
| Shop By Price     | `[builder-id="builder-cb661173..."]`                           |
| Shop By Condition | `[builder-id="builder-d6802d0f..."]`                           |
| Shop By Category  | `[builder-id="builder-712e06a7..."]`                           |
| Brands We Love    | `[builder-id="builder-c8ac2ae9..."]`                           |
| Footer            | `#footercontent` or `footer`                                   |

---

## Page Models (Content Types)

### Builder Models Used

| Model                | Content ID                         | Purpose               |
| -------------------- | ---------------------------------- | --------------------- |
| `page`               | `a77040205c244b0abe24b5f4d630421c` | Main page content     |
| `alert-bar-workers`  | `d64b1b12c5b84bf5bd0cc560474e77f4` | Top alert bar         |
| `affiliate-nav-bar`  | `bb8e818e29cf48bfbb6522f35edb3bae` | Health categories nav |
| `footer`             | `16537de034464a9d8d4633524ed45b7e` | Footer content        |
| `nav-drawer-content` | `95edb43d8d884a9aa24e350856384c61` | Mobile navigation     |
| `account-dropdown`   | `24cde185c64247c9a43004d31f8ed122` | Account popover       |

---

## Page Metadata

```javascript
{
  "title": "Shop Over 2500 FSA Eligible Products and Services",
  "description": "Page",
  "pageType": "HomePage",
  "hideLayoutFooter": false,
  "path": "/",
  "locale": "en-US",
  "currency": "USD",
  "site": "FSA Store",
  "robots": "index, follow",
  "googleSiteVerification": "dEOKOH9jX6wPUXta-FfUUcEYyc9GqhyWHghbCt1o-RE"
}
```

---

## Analytics & Tracking

| Platform           | ID/Key                                 |
| ------------------ | -------------------------------------- |
| Google Tag Manager | `GTM-K4TL22P`                          |
| Constructor.io     | `key_kWFGqMuw8gvfhv87`                 |
| Bloomreach         | `https://analytics-api.fsastore.com`   |
| AB Tasty           | `90f64213b29a76219569f9b9a8d26cf1`     |
| Zendesk            | `471b3c5d-bf07-4a04-af89-77cee1e02153` |
| TrustArc           | `fsastore.com`                         |

---

## Knowledge Graph Summary

```
FSA Store Homepage
├── Type: E-Commerce Homepage
├── Industry: Healthcare / FSA Products
├── Key Features:
│   ├── Search
│   ├── Category Navigation
│   ├── Product Discovery
│   ├── Brand Showcase
│   ├── Promotional Banners
│   └── Email Capture
├── Target Audience:
│   ├── FSA/HSA Account Holders
│   ├── Health-Conscious Consumers
│   └── Employers/HR Representatives
└── Primary CTAs:
    ├── Shop Now (Hero)
    ├── Sign Up (Email)
    ├── Shop All Brands
    └── Explore Categories
```
