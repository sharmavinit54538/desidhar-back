# DesiDhar E-Commerce API Mapping

## Frontend ↔ Backend Endpoint Mapping

### Authentication
| Frontend Call | Backend Endpoint | Method | Status |
|---------------|------------------|--------|--------|
| `authApi.requestOtp` | `/auth/otp/request` | POST | ✅ Working |
| `authApi.verifyOtp` | `/auth/otp/verify` | POST | ✅ Working |
| `authApi.me` | `/me` | GET | ✅ Working |
| `authApi.adminLogin` | `/admin/auth/login` | POST | ✅ Working |

### Catalog & Products
| Frontend Call | Backend Endpoint | Method | Status |
|---------------|------------------|--------|--------|
| `catalogQueries.categories` | `/categories` | GET | ✅ Working |
| `catalogQueries.products` | `/products` | GET | ✅ Working |
| `catalogQueries.product` | `/products/{slug}` | GET | ✅ Working |
| `adminProductsService.list` | `/admin/products` | GET | ✅ Working (page_size ≤ 50) |
| `adminProductsService.get` | `/admin/products/{id}` | GET | ✅ Working |
| `adminProductsService.create` | `/admin/products` | POST | ✅ Working |
| `adminProductsService.update` | `/admin/products/{id}` | PATCH | ✅ Working |
| `adminProductsService.delete` | `/admin/products/{id}` | DELETE | ✅ Working |

### Cart
| Frontend Call | Backend Endpoint | Method | Status |
|---------------|------------------|--------|--------|
| `cartApi.validate` | `/cart/validate` | POST | ✅ Working |
| `accountApi.quote` (uses cart) | `/checkout/preview` | POST | ✅ Working |

### Addresses
| Frontend Call | Backend Endpoint | Method | Status |
|---------------|------------------|--------|--------|
| `accountQueries.addresses` | `/addresses` | GET | ✅ Working |
| `accountApi.addAddress` | `/addresses` | POST | ✅ Working |
| `accountApi.deleteAddress` | `/addresses/{id}` | DELETE | ✅ Working |

### Checkout & Orders
| Frontend Call | Backend Endpoint | Method | Status |
|---------------|------------------|--------|--------|
| `accountApi.quote` | `/checkout/preview` | POST | ✅ Working |
| `accountApi.placeOrder` | `/orders` | POST | ✅ Working (returns payment_url) |
| `accountQueries.orders` | `/orders` | GET | ✅ Working |
| `accountQueries.order` | `/orders/{id}` | GET | ✅ Working |

### Payments
| Frontend Call | Backend Endpoint | Method | Status |
|---------------|------------------|--------|--------|
| `accountApi.placeOrder` (triggers) | `/orders/{id}/pay` | POST | ✅ Working |
| Frontend redirect | `/payments/verify` | POST | ✅ Working |
| Razorpay webhook | `/payments/webhook` | POST | ✅ Working |
| `accountQueries.paymentMethods` | `/payments/methods` | GET | ✅ Working |

### Admin - Orders
| Frontend Call | Backend Endpoint | Method | Status |
|---------------|------------------|--------|--------|
| `adminOrdersService.list` | `/admin/orders` | GET | ✅ Working |
| `adminOrdersService.get` | `/admin/orders/{id}` | GET | ✅ Working |
| `adminOrdersService.updateStatus` | `/admin/orders/{id}/status` | POST | ✅ Working |
| `adminOrdersService.createRefund` | `/admin/orders/{id}/refunds` | POST | ✅ Working |
| `adminOrdersService.getRefunds` | `/admin/orders/{id}/refunds` | GET | ✅ Working |
| `adminOrdersService.cancelExpired` | `/admin/orders/cancel-expired` | POST | ✅ Working |

### Admin - Coupons
| Frontend Call | Backend Endpoint | Method | Status |
|---------------|------------------|--------|--------|
| `adminCouponsService.list` | `/admin/coupons` | GET | ✅ Working |
| `adminCouponsService.create` | `/admin/coupons` | POST | ✅ Working |
| `adminCouponsService.update` | `/admin/coupons/{id}` | PATCH | ✅ Working |
| `adminCouponsService.delete` | `/admin/coupons/{id}` | DELETE | ✅ Working |

### Admin - Categories
| Frontend Call | Backend Endpoint | Method | Status |
|---------------|------------------|--------|--------|
| `adminCategoriesService.list` | `/admin/categories` | GET | ✅ Working |
| `adminCategoriesService.create` | `/admin/categories` | POST | ✅ Working |
| `adminCategoriesService.update` | `/admin/categories/{id}` | PATCH | ✅ Working |
| `adminCategoriesService.delete` | `/admin/categories/{id}` | DELETE | ✅ Working |

### Admin - Pincodes
| Frontend Call | Backend Endpoint | Method | Status |
|---------------|------------------|--------|--------|
| `adminPincodesService.list` | `/admin/pincodes` | GET | ✅ Working |
| `adminPincodesService.create` | `/admin/pincodes` | POST | ✅ Working |
| `adminPincodesService.update` | `/admin/pincodes/{id}` | PATCH | ✅ Working |
| `adminPincodesService.delete` | `/admin/pincodes/{id}` | DELETE | ✅ Working |
| `adminPincodesService.bulkUpsert` | `/admin/pincodes/bulk` | POST | ✅ Working |
| `adminPincodesService.importCsv` | `/admin/pincodes/import` | POST | ✅ Working |

### Delivery & Pincodes
| Frontend Call | Backend Endpoint | Method | Status |
|---------------|------------------|--------|--------|
| `deliveryApi.checkPincode` | `/pincodes/check/{pincode}` | GET | ✅ Working |
| `delivery/check` | `/delivery/check` | GET | ✅ Working |

### Contact
| Frontend Call | Backend Endpoint | Method | Status |
|---------------|------------------|--------|--------|
| `contactApi.send` | `/contact` | POST | ✅ Working (new) |

### Admin Auth
| Frontend Call | Backend Endpoint | Method | Status |
|---------------|------------------|--------|--------|
| `adminAuthService.ping` | `/admin/ping` | GET | ✅ Working |

## Response Format Compatibility

### Product Response
Backend returns `ProductOut` with fields: id, category, name, slug, description, price_paise, mrp_paise, unit, pack_size, stock_qty, images[], etc.
Frontend `normalizeProduct()` handles conversion to frontend `Product` type with variants array.

### Checkout Preview Response
Backend returns `CheckoutPreviewOut` with: subtotal, delivery_fee, discount, total, can_checkout, blocking_reasons, cod_available, etc.
Frontend `mapCheckoutPreview()` handles field name variations and paise/rupee conversion.

### Order Response
Backend returns `PlaceOrderResponse` with: order (OrderOut), payment_url (for online payments).
Frontend `validatePlacedOrder()` validates order status and payment_url format.

### Payment Methods Response
Backend returns `PaymentMethodOut[]` with: code, label, description, etc.
Frontend `PaymentMethod` type matches required fields.

## Breaking Changes from Original
1. `/orders` POST now returns `PlaceOrderResponse` instead of `OrderOut` directly
2. `/payments/verify` now requires user ownership validation
3. Admin products list limited to page_size ≤ 50 (was 100 in frontend)
4. Rate limiting added to auth endpoints

## Missing Endpoints (Now Implemented)
- `/contact` POST - Contact form submission
- `/admin/ping` GET - Admin session validation (was missing)
- `/me` GET - Customer profile (existed)
- `/pincodes/check/{pincode}` GET - Pincode serviceability (existed)