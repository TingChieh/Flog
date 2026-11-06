# Serving uploads with Caddy

Uploads live in their own directory on the server, `/var/www/flog-uploads`
(`UPLOAD_FOLDER` in the app's `.env`), next to the other sites' roots under
`/var/www`, so they are easy to find and Caddy can read them without opening
up a home directory.

`/files/…` is plain static content: stored names are random and never
rewritten, so Caddy answers from disk (with ETag, `304` and Range support) and
only hands a request to the app when the file is not there. That fallback is
what creates the resized WebP copies (`/files/_w/<width>/<name>.webp`) on first
request; after that Caddy serves them directly.

Deployed in `/etc/caddy/sites.d/aisaka-legacy.caddy` (validated with
`caddy validate`, then `systemctl reload caddy`):

```caddy
blog.aisaka.cc {
	encode gzip zstd

	handle /files/* {
		route {
			header ?Cache-Control "public, max-age=31536000, immutable"
			uri strip_prefix /files
			file_server {
				root /var/www/flog-uploads      # = UPLOAD_FOLDER
				pass_thru                       # no file: continue below
			}
			rewrite * /files{uri}
			reverse_proxy 127.0.0.1:8001
		}
	}

	handle {
		reverse_proxy 127.0.0.1:8001
	}
}
```

Notes

- The directory must be readable by the `caddy` user (mode 755, files 644).
  `/home/ubuntu` is 750, which is why uploads are not under it.
- `header ?Cache-Control` only sets the header when the response has none, so
  the app's own header on a freshly made variant is left alone. A 404 gets the
  header too, which is harmless: stored names are random, so a missing URL
  never becomes valid later.
- Without the `file_server` block everything still works through the app, just
  slower. If the directory is ever missing, requests fall through to the app.
- Variants live under `/var/www/flog-uploads/_w/`. They are disposable:
  deleting the folder only means they are rebuilt on demand. Deleting an image
  from the library removes its variants and Live Photo clip too.
- Moving the uploads: copy the directory (`rsync -a`), set `UPLOAD_FOLDER` in
  `.env`, restart `flog`, then rsync once more for anything uploaded meanwhile.
