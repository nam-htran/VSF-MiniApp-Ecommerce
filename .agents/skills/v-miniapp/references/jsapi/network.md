# Network APIs

APIs for HTTP requests and network operations.

---

## request

**When to use:** Make HTTP/HTTPS requests.

**Basic usage (async):**
```tsx
const response = await apisAsync.request({
  url: 'https://api.example.com/data',
  method: 'GET',
  headers: {
    'Content-Type': 'application/json'
  }
})

// POST request
const result = await apisAsync.request({
  url: 'https://api.example.com/submit',
  method: 'POST',
  data: { name: 'John' },
  dataType: 'json'
})
```

**Key options:**
- `url`: `string` - Request URL
- `method`: `'GET' | 'POST' | 'PUT' | 'DELETE' | ...` - HTTP method (default: `'GET'`)
- `headers`: `Record<string, string>` - Request headers
- `data`: `any` - Request body data
- `dataType`: `'json' | 'text' | ...` - Expected response data type

**Returns:** Response data (format depends on `dataType`).

**Note:** Supports standard HTTP methods. Response format depends on `dataType` option.
