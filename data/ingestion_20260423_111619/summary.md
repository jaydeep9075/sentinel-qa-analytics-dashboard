# Ingestion Summary: ingestion_20260423_111619

**Ingested at:** 2026-04-23T11:16:28.748539+00:00
**Total records ingested:** 21

## 📊 Test Metrics
- **Total number of tests:** 21
- **Executed tests:** 21 (passed + failed)
- **Skipped/Pending tests:** 0
- **Passed tests:** 8
- **Failed tests:** 13
- **Pass rate (executed only):** 38.10%
- **Average duration:** 363.03 seconds
- **Total duration:** 7623.72 seconds
- **Most common failure reason:** TimeoutError: locator.click: Timeout 20000ms exceeded.
Call log:
  - waiting for locator('.sod_label')
    - locator resolved to <span class="sod_label" title="HSA Store">HSA Store</span>
  - attempti

### 🐢 Top 15 Slowest Tests
| Test Name | Duration (seconds) |
|-----------|--------------------|
| Platforms/SOM_OCI/HSA/SOM_Payment.spec.ts#SOM_AddPayment @hsa_storefront @paymen... | 453.94 |
| Platforms/SOM_OCI/HSA/SOM_UserType.spec.ts#SOM_userType @hsa_storefront @user_ty... | 410.71 |
| Platforms/SOM_OCI/FSA/SOM_OrderDetails.spec.ts#SOM_OrderAmount_SOM_ProductSku @f... | 407.58 |
| Platforms/SOM_OCI/WDH/SOM_OrderDetails.spec.ts#SOM_OrderAmount_SOM_ProductSku @w... | 402.46 |
| Platforms/SOM_OCI/HSA/SOM_OrderDetails.spec.ts#SOM_OrderAmount_SOM_ProductSku @h... | 392.14 |
| Platforms/SFRA/Backoffice_BM/FSA/SFCC_paymentDetails.spec.ts#SFCC_PaymentDetails... | 382.46 |
| Platforms/SFRA/Backoffice_BM/HSA/SFCC_paymentDetails.spec.ts#SFCC_PaymentDetails... | 379.20 |
| Platforms/SOM_OCI/FSA/SOM_Payment.spec.ts#SOM_AddPayment @fsa_storefront @paymen... | 377.14 |
| Platforms/SFRA/Backoffice_BM/FSA/SFCC_PaymentStatus.spec.ts#SFCC_PaymentStatus @... | 376.68 |
| Platforms/SOM_OCI/FSA/SOM_UserType.spec.ts#SOM_userType @fsa_storefront @user_ty... | 373.72 |
| Platforms/SOM_OCI/WDH/SOM_Payment.spec.ts#SOM_AddPayment @wdh_storefront @paymen... | 372.35 |
| Platforms/SOM_OCI/WDH/SOM_OrderDetails.spec.ts#SOM_OrderAmount_SOM_ProductSku @w... | 361.81 |
| Platforms/SOM_OCI/HSA/SOM_OrderDetails.spec.ts#SOM_OrderAmount_SOM_ProductSku @h... | 359.87 |
| Platforms/SOM_OCI/FSA/SOM_OrderDetails.spec.ts#SOM_OrderAmount_SOM_ProductSku @f... | 356.63 |
| Platforms/SOM_OCI/WDH/SOM_UserType.spec.ts#SOM_userType @wdh_storefront @user_ty... | 350.09 |

## 📁 Tables in this ingestion
- `documents`
- `sources`
- `structured_test_results`