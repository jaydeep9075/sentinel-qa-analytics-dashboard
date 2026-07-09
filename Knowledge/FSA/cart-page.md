# Cart Page

## Purpose

This page is the shopping cart experience where users review selected items, see pricing, and proceed toward checkout.

## Page Summary

- URL: /cart
- Page type: Cart and checkout preparation page
- Primary goal: help users confirm items, adjust quantities, review totals, and move to checkout.

## Main Page Structure

1. Shared site header and navigation
2. Cart item list
3. Order summary and pricing details
4. Promotional or account-related reminder content
5. Saved-for-later area if present
6. Related product recommendations
7. Shared footer

## Key Content Areas

- The page focuses on item review and purchase readiness.
- Users can update quantities, remove items, save items for later, and see order totals.
- The experience is transactional and should be interpreted as a conversion step rather than a content page.

## Agent and LLM Notes

Use this document as the canonical reference for cart-page intent, structure, and the main user tasks involved in preparing checkout.

## Related Knowledge

- Shared navigation: [navigation-menu.md](navigation-menu.md)
- Shared footer: [footer.md](footer.md)

| Feature          | Description                                  |
| ---------------- | -------------------------------------------- |
| Email Signup     | Email input + "Sign Up" button               |
| Trust Badge      | "100% Eligibility Guarantee" with icon       |
| LegitScript Seal | Verifies LegitScript Approval                |
| Payment Icons    | Visa, Mastercard, Amex, Discover             |
| Copyright        | "© 2026 FSA Store Inc. All Rights Reserved." |

---

### 3.4 Legal & Compliance Links

| #   | Link Text                   | Destination                                 |
| --- | --------------------------- | ------------------------------------------- |
| 1   | Terms of Use                | `/terms-and-conditions.html`                |
| 2   | Privacy Notice              | `/privacy-policy.html`                      |
| 3   | California Privacy Notice   | `/privacy-notice-california-residents.html` |
| 4   | Consumer Health Data Notice | `/consumer-health-data-notice.html`         |
| 5   | Accessibility               | `#` (opens accessibility tool)              |
| 6   | Cookie Preferences          | `#` (opens cookie settings)                 |

---

## Section 4: Global Elements

### 4.1 Live Chat

| Property         | Value                      |
| ---------------- | -------------------------- |
| Position         | Fixed, bottom right corner |
| Background Color | `#ff295b` (pink)           |
| Text             | "Chat"                     |
| Action           | Opens Zendesk chat widget  |
| Icon             | Chat bubble icon           |

---

### 4.2 Cookie Banner

| Property     | Value                                                            |
| ------------ | ---------------------------------------------------------------- |
| Position     | Fixed, bottom of screen                                          |
| Close Button | "X" icon in top-right corner                                     |
| Content      | Cookie policy message with Privacy Notice and Terms of Use links |

**Message:** "We use cookies to provide you with the best online experience. If you continue browsing, we consider that you accept our Cookie Policy, and also agree to the terms of our Privacy Notice and Terms of Use."

---

### 4.3 Developer Panel

| Property | Value                             |
| -------- | --------------------------------- |
| Position | Fixed, bottom left corner         |
| Icon     | Settings gear                     |
| Color    | `#55449a` (purple)                |
| Purpose  | Access to developer configuration |

---

## Analytics & Tracking

| Platform           | ID/Key                                 |
| ------------------ | -------------------------------------- |
| Google Tag Manager | `GTM-K4TL22P`                          |
| Constructor.io     | `key_kWFGqMuw8gvfhv87`                 |
| Bloomreach         | `https://analytics-api.fsastore.com`   |
| AB Tasty           | `90f64213b29a76219569f9b9a8d26cf1`     |
| Zendesk            | `471b3c5d-bf07-4a04-af89-77cee1e02153` |

---

## Key Page Interactions

| Action                        | Result                                                    |
| ----------------------------- | --------------------------------------------------------- |
| Click "Sign in"               | Opens account popover with login options                  |
| Click "Continue to Checkout"  | Redirects to checkout login                               |
| Enter promo code + Apply      | Validates and applies discount                            |
| Click "+" quantity button     | Increases item quantity                                   |
| Click "-" quantity button     | Decreases item quantity (disables at 1)                   |
| Click "Remove" button         | Removes item from cart                                    |
| Click "Save for later"        | Moves item to saved list                                  |
| Click "Edit"                  | Redirects to product page in edit mode                    |
| Click product name/image      | Redirects to product detail page                          |
| Click "Add" on recommendation | Adds recommended product to cart                          |
| Click "Quick View"            | Opens quick view modal for product                        |
| Click "Chat" button           | Opens Zendesk live chat widget                            |
| Click "FAQ"                   | Redirects to help center                                  |
| Use search bar                | Shows autocomplete suggestions, submits to search results |
| Log in                        | Unlocks member-only rewards and savings                   |

---

## Builder.io Blocks

| Block ID                                   | Purpose                | Model               |
| ------------------------------------------ | ---------------------- | ------------------- |
| `builder-ff6a342cfdb8408587464d65abc46173` | Top bar / alert bar    | `alert-bar-workers` |
| `builder-18b4c6e1a1c24631a1564d3f655a7ad9` | Core slider navigation | -                   |
| `builder-2066bb1f33414697936ac872cfd5e675` | SOW navigation         | -                   |
| `builder-31b2634acd9a48c59a634b37cddba03e` | Auxiliary navigation   | `affiliate-nav-bar` |
| `builder-214bc054d1824e45b20b6dfafb3f8cd0` | Footer                 | `footer`            |
| `builder-b9cb4a7962b04ca6822a155acc6cf6e4` | Live chat button       | -                   |
| `builder-d396ce6037b142e88c21f6c01197e008` | Cookie banner          | -                   |
