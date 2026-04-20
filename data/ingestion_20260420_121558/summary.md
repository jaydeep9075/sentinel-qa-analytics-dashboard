# Ingestion Summary: ingestion_20260420_121558

**Ingested at:** 2026-04-20T12:16:08.908174+00:00
**Total records ingested:** 1

## 📊 Test Metrics
- **Total number of tests:** 306
- **Passed tests:** 260
- **Failed tests:** 45
- **Pass rate:** 84.97%
- **Average duration:** 189.63 seconds
- **Total duration:** 58026.44 seconds
- **Most common failure reason:** Error: Action failed after 3 attempts - Error: TimeoutError: locator.click: Timeout 30000ms exceeded.
Call log:
  - waiting for getByRole('link', { name: 'SignIn' }).first()

### 🐢 Top 15 Slowest Tests
| Test Name | Duration (seconds) |
|-----------|--------------------|
| Platforms/SFRA/Checkout/HSA/RestartedRegisteredCheckout.spec.ts#RestartedCheckou... | 520.90 |
| Platforms/SFRA/Checkout/FSA/RestartedRegisteredCheckout.spec.ts#RestartedCheckou... | 520.39 |
| Platforms/SFRA/Checkout/WDH/RestartedRegisteredCheckout.spec.ts#RestartedCheckou... | 498.78 |
| Platforms/SFRA/Checkout/HSA/RestartedGuestCheckout.spec.ts#RestartedCheckout @hs... | 444.66 |
| Platforms/SFRA/Checkout/FSA/RestartedGuestCheckout.spec.ts#RestartedCheckout @fs... | 433.01 |
| Platforms/SFRA/Order History_Status/FSA/OrderHistory.spec.ts#OrderHistoryTest @f... | 433.00 |
| Platforms/SFRA/Order History_Status/FSA/OrderHistory.spec.ts#OrderHistoryTest @f... | 432.23 |
| Platforms/SFRA/Favorites Feature/FSA/AddToFavorites.spec.ts#AddToFavorites @fsa_... | 428.64 |
| Platforms/SFRA/Favorites Feature/HSA/AddToFavorites.spec.ts#AddToFavorites @hsa_... | 427.40 |
| Platforms/SFRA/Order History_Status/HSA/OrderHistory.spec.ts#OrderHistoryTest @h... | 418.87 |
| Platforms/SFRA/Order History_Status/HSA/OrderHistory.spec.ts#OrderHistoryTest @h... | 415.85 |
| Platforms/SFRA/Favorites Feature/WDH/AddToFavorites.spec.ts#AddToFavorites @wdh_... | 399.81 |
| Platforms/SFRA/Order History_Status/WDH/OrderHistory.spec.ts#OrderHistoryTest @w... | 399.71 |
| Platforms/SFRA/Favorites Feature/FSA/AddToFavorites.spec.ts#AddToFavorites @fsa_... | 397.72 |
| Platforms/SFRA/Favorites Feature/HSA/AddToFavorites.spec.ts#AddToFavorites @hsa_... | 397.08 |

## 📁 Tables in this ingestion
- `documents`
- `sources`
- `structured_test_results`