# File & Network APIs

APIs for file download, upload, and cloud operations.

---

## downloadFile

**When to use:** Download file from URL.

**Basic usage (async):**
```tsx
const result = await apisAsync.downloadFile({
  url: 'https://example.com/file.pdf'
})
// result.tempFilePath - downloaded file path
```

**Key options:**
- `url`: `string` - File URL to download

**Returns:**
- `tempFilePath`: `string` - Path to downloaded file

---

## uploadFile

**When to use:** Upload file to server.

**Basic usage (async):**
```tsx
const result = await apisAsync.uploadFile({
  url: 'https://api.example.com/upload',
  filePath: '/path/to/file.jpg',
  name: 'file',
  formData: {
    userId: '123'
  }
})
```

**Key options:**
- `url`: `string` - Upload endpoint URL
- `filePath`: `string` - Local file path to upload
- `name`: `string` - Form field name for file
- `formData`: `Record<string, any>` - Additional form data

**Returns:** Upload response from server.

---

## Cloud Upload

**When to use:** Upload file to cloud storage (V-App cloud service).

**Note:** Check API documentation for cloud upload specific API if available.
