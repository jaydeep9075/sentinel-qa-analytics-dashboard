# Ingestion Summary: ingestion_20260422_043922

**Ingested at:** 2026-04-22T04:39:33.875477+00:00
**Total records ingested:** 1

## 📊 Test Metrics
- **Total number of tests:** 35
- **Passed tests:** 8
- **Failed tests:** 27
- **Pass rate:** 22.86%
- **Average duration:** 345.61 seconds
- **Total duration:** 12096.44 seconds
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
| Platforms/SOM_OCI/HSA/SOM_Payment.spec.ts#SOM_AddPayment @hsa_storefront @paymen... | 406.01 |
| Platforms/SOM_OCI/HSA/SOM_UserType.spec.ts#SOM_userType @hsa_storefront @user_ty... | 402.49 |
| Platforms/SOM_OCI/WDH/SOM_OrderDetails.spec.ts#SOM_OrderAmount_SOM_ProductSku @w... | 402.46 |
| Platforms/SOM_OCI/HSA/SOM_OrderDetails.spec.ts#SOM_OrderAmount_SOM_ProductSku @h... | 392.14 |
| Platforms/SFRA/Backoffice_BM/FSA/SFCC_paymentDetails.spec.ts#SFCC_PaymentDetails... | 382.46 |
| Platforms/SFRA/Backoffice_BM/HSA/SFCC_paymentDetails.spec.ts#SFCC_PaymentDetails... | 379.20 |
| Platforms/SOM_OCI/FSA/SOM_Payment.spec.ts#SOM_AddPayment @fsa_storefront @paymen... | 377.14 |
| Platforms/SFRA/Backoffice_BM/FSA/SFCC_PaymentStatus.spec.ts#SFCC_PaymentStatus @... | 376.68 |
| Platforms/SOM_OCI/FSA/SOM_UserType.spec.ts#SOM_userType @fsa_storefront @user_ty... | 373.72 |
| Platforms/SOM_OCI/WDH/SOM_Payment.spec.ts#SOM_AddPayment @wdh_storefront @paymen... | 372.35 |
| Platforms/SOM_OCI/FSA/SOM_Payment.spec.ts#SOM_AddPayment @fsa_storefront @paymen... | 372.06 |
| Platforms/SOM_OCI/WDH/SOM_OrderDetails.spec.ts#SOM_OrderAmount_SOM_ProductSku @w... | 361.81 |

## 📁 Tables in this ingestion
- `documents`
- `sources`
- `structured_test_results`