# Ingestion Summary: ingestion_20260709_110143

**Ingested at:** 2026-07-09T11:03:01.319927+00:00
**Total records ingested:** 708

## 📊 Test Metrics
- **Total number of tests:** 610
- **Executed tests:** 608 (passed + failed)
- **Skipped/Pending tests:** 2
- **Passed tests:** 510
- **Failed tests:** 98
- **Pass rate (executed only):** 83.88%
- **Average duration:** 227.31 seconds
- **Total duration:** 138656.52 seconds
- **Most common failure reason:** TimeoutError: locator.textContent: Timeout 20000ms exceeded.
Call log:
  - waiting for locator('xpath=(//div[@class=\'c-account__card__body card-body\'])[1]/dl[3]/dd')

### 🐢 Top 15 Slowest Tests
| Test Name | Duration (seconds) |
|-----------|--------------------|
| Platforms/SFRA/Perks Feature/FSA/EarnPointsBySpend.spec.ts#EarnPointsBySpend @fs... | 1179.21 |
| Platforms/SFRA/Checkout/WDH/RestartedRegisteredCheckout.spec.ts#RestartedCheckou... | 832.51 |
| Platforms/SFRA/Perks Feature/FSA/EarnPointsBySpend.spec.ts#EarnPointsBySpend @fs... | 820.84 |
| Platforms/SFRA/Checkout/FSA/RestartedRegisteredCheckout.spec.ts#RestartedCheckou... | 820.17 |
| Platforms/SFRA/Checkout/FSA/SplitPayWithPerksStoreCreditCoupon.spec.ts#SplitPayW... | 710.90 |
| Platforms/SFRA/Favorites Feature/WDH/AddToFavorites.spec.ts#AddToFavorites @wdh_... | 692.29 |
| Platforms/SFRA/Favorites Feature/WDH/AddToFavorites.spec.ts#AddToFavorites @wdh_... | 683.96 |
| Platforms/SFRA/Checkout/FSA/SplitPayWithPerkStoreCredit.spec.ts#SplitPayWithPerk... | 678.99 |
| Platforms/SFRA/Order History_Status/WDH/OrderStatus.spec.ts#OrderStatusTest @wdh... | 677.59 |
| Platforms/SFRA/Favorites Feature/FSA/AddToFavorites.spec.ts#AddToFavorites @fsa_... | 674.22 |
| Platforms/SFRA/Order History_Status/WDH/OrderHistory.spec.ts#OrderHistoryTest @w... | 666.92 |
| Platforms/SFRA/Order History_Status/FSA/OrderHistory.spec.ts#OrderHistoryTest @f... | 661.95 |
| Platforms/SFRA/Checkout/HSA/RestartedGuestCheckout.spec.ts#RestartedCheckout @hs... | 649.66 |
| Platforms/SFRA/Checkout/FSA/RestartedGuestCheckout.spec.ts#RestartedCheckout @fs... | 645.34 |
| Platforms/SFRA/Favorites Feature/WDH/AddToFavorites.spec.ts#AddToFavorites @wdh_... | 644.90 |

## 📁 Tables in this ingestion
- `documents`
- `sources`
- `structured_test_module_metrics`
- `structured_test_project_metrics`
- `structured_test_results`