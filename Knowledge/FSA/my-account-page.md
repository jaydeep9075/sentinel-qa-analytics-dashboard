# My Account Page

## Purpose

This page is the authenticated account dashboard where users can manage profile information, saved items, rewards, and account-related actions.

## Page Summary

- URL: https://fsa.devhec.com/my-account
- Page type: Account dashboard
- Primary goal: help signed-in users review account details, manage preferences, access rewards, and continue shopping.

## Main Page Structure

1. Shared site header and navigation
2. Account summary and profile sections
3. Personal information and address management area
4. Rewards or loyalty information
5. Favorites or saved-items section
6. Payment and account management links
7. Shared footer

## Key Content Areas

- The page is centered on account management and personalized experience.
- It supports actions such as updating profile information, reviewing saved items, and accessing rewards and order-related functions.
- It should be understood as a private, authenticated workspace rather than a public content page.

## Agent and LLM Notes

Treat this page as the main account hub for the FSA Store experience. It should be referenced when understanding user identity, account state, rewards, and post-login actions.

## Related Knowledge

- Shared navigation: [navigation-menu.md](navigation-menu.md)
- Shared footer: [footer.md](footer.md)

│ ├── Favorites ──────────────────────────────────→ /favorites │
│ ├── Track & Manage Orders ──────────────────────→ /orders-new │
│ ├── FSA Perks® Dashboard ──────────────────────→ /loyalty-perks │
│ ├── Buy It Again & Recommendations ────────────→ /personalized-picks.html│
│ ├── Help / Contact Us ──────────────────────────→ /about-fsa-store-contactus.html│
│ └── Sign Out ───────────────────────────────────→ /logout │
└─────────────────────────────────────────────────────────────────────────────┘

```

### Product Recommendation Interaction

```

┌─────────────────────────────────────────────────────────────────────────────┐
│ TOP PICKS FOR YOU (Carousel) │
├─────────────────────────────────────────────────────────────────────────────┤
│ │
│ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ │
│ │ Product │ │ Product │ │ Product │ │ Product │ │ Product │ │
│ │ Image │ │ Image │ │ Image │ │ Image │ │ Image │ │
│ │ Rating │ │ Rating │ │ Rating │ │ Rating │ │ Rating │ │
│ │ Price │ │ Price │ │ Price │ │ Price │ │ Price │ │
│ │ [Add] │ │ [Add] │ │ [Add] │ │ [Add] │ │ [Add] │ │
│ └─────────┘ └─────────┘ └─────────┘ └─────────┘ └─────────┘ │
│ │
│ ◄─────────── Carousel Scrollable ───────────► │
│ │
│ Click on product → Quick View Modal or Product Detail Page │
│ Click [Add] → Adds to Cart │
└─────────────────────────────────────────────────────────────────────────────┘

```

### Quick View Modal Flow

```

┌─────────────────────────────────────────────────────────────────────────────┐
│ QUICK VIEW MODAL │
├─────────────────────────────────────────────────────────────────────────────┤
│ │
│ ┌───────────────────────────────────────────────────────────────────┐ │
│ │ ✕ Close │ │
│ │ ┌────────────┐ ┌──────────────────────────────────────────┐ │ │
│ │ │ Image │ │ Product Name │ │ │
│ │ │ │ │ Rating: ★★★★☆ │ │ │
│ │ │ │ │ Price: $XX.XX │ │ │
│ │ │ │ │ Quantity: [-] [1] [+] │ │ │
│ │ │ │ │ [Add to Cart] │ │ │
│ │ └────────────┘ └──────────────────────────────────────────┘ │ │
│ └───────────────────────────────────────────────────────────────────┘ │
│ │
│ Actions: │
│ • Click product image → Product Detail Page │
│ • Click "Add to Cart" → Adds to cart, closes modal │
│ • Click ✕ or outside modal → Close modal │
│ • Click product name → Product Detail Page │
└─────────────────────────────────────────────────────────────────────────────┘

```

### Search Autocomplete Flow

```

┌─────────────────────────────────────────────────────────────────────────────┐
│ SEARCH INPUT (Constructor.io) │
├─────────────────────────────────────────────────────────────────────────────┤
│ │
│ ┌─────────────────────────────────────────────────────────────────────┐ │
│ │ 🔍 [Search Eligible Products...] [✕] [🔍 Submit] │ │
│ └─────────────────────────────────────────────────────────────────────┘ │
│ │ │
│ ▼ │
│ ┌─────────────────────────────────────────────────────────────────────┐ │
│ │ Search Suggestions │ │
│ │ ├── Suggestion 1 │ │
│ │ ├── Suggestion 2 │ │
│ │ └── Suggestion 3 │ │
│ ├─────────────────────────────────────────────────────────────────────┤ │
│ │ Products │ │
│ │ ├── [Image] Product Name 1 $XX.XX │ │
│ │ ├── [Image] Product Name 2 $XX.XX │ │
│ │ └── [Image] Product Name 3 $XX.XX │ │
│ ├─────────────────────────────────────────────────────────────────────┤ │
│ │ Articles │ │
│ │ ├── Article 1 │ │
│ │ └── Article 2 │ │
│ └─────────────────────────────────────────────────────────────────────┘ │
│ │
│ Actions: │
│ • Type query → Shows autocomplete suggestions │
│ • Click suggestion → Search results page with query │
│ • Click product → Navigate to product detail page │
│ • Click article → Navigate to article page │
│ • Click ✕ → Clears search input │
│ • Click Submit → Search results page │
│ • Press Enter → Search results page │
└─────────────────────────────────────────────────────────────────────────────┘

```

---

## Dependency Graph

```

                                    ┌─────────────────┐
                                    │   PAGE LOAD     │
                                    └────────┬────────┘
                                             │
                    ┌────────────────────────┼────────────────────────┐
                    │                        │                        │
                    ▼                        ▼                        ▼
          ┌─────────────────┐    ┌───────────────────┐    ┌───────────────────┐
          │  User Session   │    │  Data Layer       │    │  Analytics        │
          │  Validation     │    │  Population       │    │  Tracking         │
          └────────┬────────┘    └───────────────────┘    └───────────────────┘
                   │                      │                        │
                   ▼                      ▼                        ▼
          ┌─────────────────────────────────────────────────────────────────┐
          │                          API CALLS                              │
          ├─────────────────────────────────────────────────────────────────┤
          │                                                                 │
          │  ┌─────────────────────────────────────────────────────────┐   │
          │  │  Account Data        │  → User profile, addresses       │   │
          │  ├─────────────────────────────────────────────────────────┤   │
          │  │  Perks Data          │  → Points, tier, activity        │   │
          │  ├─────────────────────────────────────────────────────────┤   │
          │  │  Favorites Data      │  → Wishlist items                │   │
          │  ├─────────────────────────────────────────────────────────┤   │
          │  │  Payment Data        │  → Saved payment methods         │   │
          │  ├─────────────────────────────────────────────────────────┤   │
          │  │  Recommendations     │  → Constructor.io recommendations│   │
          │  └─────────────────────────────────────────────────────────┘   │
          │                                                                 │
          └─────────────────────────────────────────────────────────────────┘
                                     │
                    ┌────────────────┼────────────────┐
                    │                │                │
                    ▼                ▼                ▼
          ┌─────────────────┐┌─────────────────┐┌─────────────────────┐
          │   Header        ││   Main Content  ││      Footer         │
          │   Navigation    ││   Dashboard     ││      Information    │
          └─────────────────┘└─────────────────┘└─────────────────────┘
                    │                │                │
                    ▼                ▼                ▼
          ┌─────────────────────────────────────────────────────────────────┐
          │                         USER ACTIONS                            │
          ├─────────────────────────────────────────────────────────────────┤
          │                                                                 │
          │  ┌──────────────┐  ┌──────────────┐  ┌─────────────────────┐  │
          │  │  Navigation  │  │  Data Entry  │  │  Submit/Redirect    │  │
          │  │  Clicks      │  │  (Forms)     │  │  Actions            │  │
          │  └──────────────┘  └──────────────┘  └─────────────────────┘  │
          │                                                                 │
          └─────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
          ┌─────────────────────────────────────────────────────────────────┐
          │                         TRACKING EVENTS                          │
          ├─────────────────────────────────────────────────────────────────┤
          │                                                                 │
          │  ┌─────────────────────────────────────────────────────────┐   │
          │  │  • Segment Analytics                                    │   │
          │  │  • Google Tag Manager (GTM-K4TL22P)                    │   │
          │  │  • Bloomreach / Exponea                                │   │
          │  │  • Constructor.io Tracking                             │   │
          │  │  • Riskified (Fraud Prevention)                        │   │
          │  │  • PowerReviews (Reviews)                              │   │
          │  └─────────────────────────────────────────────────────────┘   │
          │                                                                 │
          └─────────────────────────────────────────────────────────────────┘

```

---

## Routing & Navigation Map

```

┌─────────────────────────────────────────────────────────────────────────────────────┐
│ PAGE NAVIGATION MAP │
├─────────────────────────────────────────────────────────────────────────────────────┤
│ │
│ ┌─────────────────────────────────────────────────────────────────────────────────┐│
│ │ HOME ─────────────────────────────────────────────────────→ / ││
│ └─────────────────────────────────────────────────────────────────────────────────┘│
│ │ │
│ ▼ │
│ ┌─────────────────────────────────────────────────────────────────────────────────┐│
│ │ MY ACCOUNT (Current) ─────────────────────────────────→ /my-account ││
│ ├─────────────────────────────────────────────────────────────────────────────────┤│
│ │ ├── Edit Profile ─────────────────────────────────────→ /profile ││
│ │ ├── Edit Password ────────────────────────────────────→ /Account-EditPassword ││
│ │ ├── Address Book ─────────────────────────────────────→ /addressbook ││
│ │ ├── Add Address ──────────────────────────────────────→ /add-address ││
│ │ ├── Payment Methods ──────────────────────────────────→ /wallet ││
│ │ ├── Add Payment ──────────────────────────────────────→ /add-payment ││
│ │ ├── Favorites ────────────────────────────────────────→ /favorites ││
│ │ ├── Track Orders ─────────────────────────────────────→ /orders-new ││
│ │ ├── Perks Dashboard ──────────────────────────────────→ /loyalty-perks ││
│ │ └── Sign Out ──────────────────────────────────────────→ /logout ││
│ └─────────────────────────────────────────────────────────────────────────────────┘│
│ │
│ ┌─────────────────────────────────────────────────────────────────────────────────┐│
│ │ HEADER NAVIGATION ││
│ ├─────────────────────────────────────────────────────────────────────────────────┤│
│ │ ├── Menu ───────────────────────────────────────────────────→ Toggle Sidebar ││
│ │ ├── Search ─────────────────────────────────────────────────→ Toggle Search ││
│ │ ├── Logo ──────────────────────────────────────────────────→ / ││
│ │ ├── Account Dropdown ──────────────────────────────────────→ Show User Menu ││
│ │ ├── Favorites ─────────────────────────────────────────────→ /favorites ││
│ │ └── Cart ──────────────────────────────────────────────────→ /cart ││
│ └─────────────────────────────────────────────────────────────────────────────────┘│
│ │
│ ┌─────────────────────────────────────────────────────────────────────────────────┐│
│ │ FOOTER NAVIGATION ││
│ ├─────────────────────────────────────────────────────────────────────────────────┤│
│ │ ├── Email Signup ────────────────────────────────────────→ Subscribe API ││
│ │ ├── Customer Service ────────────────────────────────────→ Various Pages ││
│ │ ├── Resources ───────────────────────────────────────────→ Various Pages ││
│ │ ├── Our Company ─────────────────────────────────────────→ External/Internal ││
│ │ ├── My Account ──────────────────────────────────────────→ Various Pages ││
│ │ ├── Legal Links ─────────────────────────────────────────→ Legal Pages ││
│ │ └── Social Links ────────────────────────────────────────→ External Sites ││
│ └─────────────────────────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────────────────────────┘

```

---

## Key Dependencies & Integrations

| Integration | Purpose | Key |
|-------------|---------|-----|
| **Constructor.io** | Search Autocomplete | key_kWFGqMuw8gvfhv87 |
| **Segment** | Analytics Tracking | poGF52EDWXhCFBTLNA1NQZKTUvVfUSbA |
| **Google Tag Manager** | Analytics/Consent | GTM-K4TL22P |
| **Bloomreach/Exponea** | Customer Data Platform | analytics-api.devhec.com |
| **TrustArc** | Consent Management | teconsent |
| **PowerReviews** | Product Reviews | PRApi: ad2d0703-16cf-4778-b046-17fd4b8537c5 |
| **Riskified** | Fraud Prevention | fsastore.com_hec_dev |
| **Zendesk** | Live Chat | 471b3c5d-bf07-4a04-af89-77cee1e02153 |
| **Agentforce (Salesforce)** | Customer Support Chat | 00Dce0000032Sl1 |
| **Loqate** | Address Validation | FSAST11112 |
| **iZooto** | Push Notifications | 79ed7621f6247b28f5eb21c410706c5c89e79c1a |
| **AB Tasty** | A/B Testing | 9ad5861e87506157d4a605e47b8e9de3 |
| **Cloudflare** | Analytics/Performance | 8af3904bf8c04863b2d4a2b8f6f15a1e |

---

## Technical Notes

### User Data
- **Customer ID:** 00294242
- **Email (Hashed):** 0b3eb0afb9cd713a4cd4c3cc46fb657f4dc15fc27a3c7dc5e275b454cd5281fb
- **Customer Groups:** Everyone, LMN Allowed, Loyalty Members, Non TPA Customers, Registered, Returning customer
- **Loyalty Status:** True (Gold Tier, 2,368 points)
- **TPA (Third Party Administrator) Access:** True

### Environment
- **Instance Type:** Development
- **Realm:** BFKW
- **Site:** FSASTORE
- **Locale:** default (en_US)
- **Sales Channel:** FSASTORE (desktop)
```
