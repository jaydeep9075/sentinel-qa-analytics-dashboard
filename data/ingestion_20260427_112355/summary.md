# Ingestion Summary: ingestion_20260427_112355

**Ingested at:** 2026-04-27T11:24:43.176584+00:00
**Total records ingested:** 712

## 📊 Test Metrics
- **Total number of tests:** 606
- **Executed tests:** 596 (passed + failed)
- **Skipped/Pending tests:** 10
- **Passed tests:** 560
- **Failed tests:** 36
- **Pass rate (executed only):** 93.96%
- **Average duration:** 238.23 seconds
- **Total duration:** 144367.96 seconds
- **Most common failure reason:** Error: Alaska/Hawaii Address Restriction message verification has Failed

expect(locator).toContainText(expected) failed

Locator: locator('.shipping-error.c-checkout__shipping-error .alert')
Expected

### 🐢 Top 15 Slowest Tests
| Test Name | Duration (seconds) |
|-----------|--------------------|
| Platforms/SFRA/Checkout/WDH/RestartedRegisteredCheckout.spec.ts#RestartedCheckou... | 861.55 |
| Platforms/SFRA/Checkout/HSA/RestartedRegisteredCheckout.spec.ts#RestartedCheckou... | 838.06 |
| Platforms/SFRA/Checkout/FSA/RestartedRegisteredCheckout.spec.ts#RestartedCheckou... | 821.79 |
| Platforms/SFRA/Checkout/WDH/SplitPayWithStoreCredit.spec.ts#SplitPayWithStoreCre... | 707.21 |
| Platforms/SFRA/Checkout/HSA/SplitPayWithPerksStoreCreditCoupon.spec.ts#SplitPayW... | 705.71 |
| Platforms/SFRA/Order History_Status/WDH/OrderStatus.spec.ts#OrderStatusTest @wdh... | 700.42 |
| Platforms/SFRA/Favorites Feature/WDH/AddToFavorites.spec.ts#AddToFavorites @wdh_... | 694.36 |
| Platforms/SFRA/Favorites Feature/WDH/AddToFavorites.spec.ts#AddToFavorites @wdh_... | 686.68 |
| Platforms/SFRA/Favorites Feature/FSA/AddToFavorites.spec.ts#AddToFavorites @fsa_... | 686.01 |
| Platforms/SFRA/Favorites Feature/HSA/AddToFavorites.spec.ts#AddToFavorites @hsa_... | 675.20 |
| Platforms/SFRA/Checkout/FSA/SplitPayWithPerkStoreCredit.spec.ts#SplitPayWithPerk... | 665.38 |
| Platforms/SFRA/Order History_Status/WDH/OrderHistory.spec.ts#OrderHistoryTest @w... | 664.86 |
| Platforms/SFRA/Checkout/HSA/SplitPayWithPerkStoreCredit.spec.ts#SplitPayWithPerk... | 653.82 |
| Platforms/SFRA/Order History_Status/WDH/OrderHistory.spec.ts#OrderHistoryTest @w... | 650.96 |
| Platforms/SFRA/Checkout/FSA/RestartedGuestCheckout.spec.ts#RestartedCheckout @fs... | 650.01 |

## 📁 Tables in this ingestion
- `documents`
- `sources`
- `structured_test_module_metrics`
- `structured_test_project_metrics`
- `structured_test_results`