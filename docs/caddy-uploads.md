# Serving uploads with Caddy

> Not validated against a real Caddy yet. Run
> `caddy validate --config /etc/caddy/Caddyfile` before reloading.

`/files/…` is plain static content: stored names are random and never
rewritten, so Caddy can answer from disk and only hand a request to Flask when
the file is not there. That fallback is what creates the resized WebP copies
(`/files/_w/<width>/<name>.webp`) on first request; after that Caddy serves
them directly.

```caddy
example.com {
	handle /files/* {
		route {
			header ?Cache-Control "public, max-age=31536000, immutable"
			uri strip_prefix /files
			file_server {
				root /srv/flog/instance/uploads      # = UPLOAD_FOLDER
				pass_thru                            # no file: continue below
			}
			rewrite * /files{uri}
			reverse_proxy 127.0.0.1:8000
		}
	}

	handle {
		reverse_proxy 127.0.0.1:8000
	}
}
```

Notes

- Adjust the upload path and the upstream address.
- `header ?Cache-Control` only sets the header when the response has none, so
  Flask's own header on a freshly made variant is left alone. A 404 gets the
  header too, which is harmless: stored names are random, so a missing URL
  never becomes valid later.
- Without the `file_server` block everything still works through Flask, just
  slower.
- Variants live under `<UPLOAD_FOLDER>/_w/`. They are disposable: deleting the
  folder only means they are rebuilt on demand. Deleting an image from the
  library removes its variants too.
