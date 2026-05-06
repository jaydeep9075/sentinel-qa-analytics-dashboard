# Ingestion Summary: ingestion_20260506_110116

**Ingested at:** 2026-05-06T11:01:52.660886+00:00
**Total records ingested:** 708

## 📊 Test Metrics
- **Total number of tests:** 610
- **Executed tests:** 608 (passed + failed)
- **Skipped/Pending tests:** 2
- **Passed tests:** 549
- **Failed tests:** 59
- **Pass rate (executed only):** 90.30%
- **Average duration:** 246.14 seconds
- **Total duration:** 150147.68 seconds
- **Most common failure reason:** Error: Action failed after 3 attempts - Error: TimeoutError: locator.click: Timeout 30000ms exceeded.
Call log:
  - waiting for getByRole('button', { name: 'Sign In' })
    - locator resolved to <butt

### 🐢 Top 15 Slowest Tests
| Test Name | Duration (seconds) |
|-----------|--------------------|
| Platforms/SFRA/Perks Feature/HSA/EarnPointsBySpend.spec.ts#EarnPointsBySpend @hs... | 1187.63 |
| Platforms/SFRA/Perks Feature/FSA/EarnPointsBySpend.spec.ts#EarnPointsBySpend @fs... | 1171.55 |
| Platforms/SFRA/Checkout/WDH/RestartedRegisteredCheckout.spec.ts#RestartedCheckou... | 883.84 |
| Platforms/SFRA/Checkout/FSA/RestartedRegisteredCheckout.spec.ts#RestartedCheckou... | 830.19 |
| Platforms/SFRA/Perks Feature/FSA/EarnPointsBySpend.spec.ts#EarnPointsBySpend @fs... | 813.69 |
| Platforms/SFRA/Checkout/HSA/RestartedRegisteredCheckout.spec.ts#RestartedCheckou... | 811.08 |
| Platforms/SFRA/Perks Feature/HSA/EarnPointsBySpend.spec.ts#EarnPointsBySpend @hs... | 767.70 |
| Platforms/SFRA/Checkout/HSA/SplitPayWithPerksStoreCreditCoupon.spec.ts#SplitPayW... | 701.14 |
| Platforms/SFRA/Favorites Feature/WDH/AddToFavorites.spec.ts#AddToFavorites @wdh_... | 693.13 |
| Platforms/SFRA/Order History_Status/WDH/OrderStatus.spec.ts#OrderStatusTest @wdh... | 689.57 |
| Platforms/SFRA/Favorites Feature/WDH/AddToFavorites.spec.ts#AddToFavorites @wdh_... | 682.91 |
| Platforms/SFRA/Favorites Feature/FSA/AddToFavorites.spec.ts#AddToFavorites @fsa_... | 680.01 |
| Platforms/SFRA/Favorites Feature/HSA/AddToFavorites.spec.ts#AddToFavorites @hsa_... | 675.96 |
| Platforms/SFRA/Checkout/HSA/RestartedGuestCheckout.spec.ts#RestartedCheckout @hs... | 673.44 |
| Platforms/SFRA/Checkout/FSA/RestartedGuestCheckout.spec.ts#RestartedCheckout @fs... | 672.12 |

## 📁 Tables in this ingestion
- `documents`
- `sources`
- `structured_test_module_metrics`
- `structured_test_project_metrics`
- `structured_test_results`