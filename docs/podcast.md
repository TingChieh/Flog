# Podcast

The podcast is a page of the blog, not a separate site: it uses the blog's menu,
name, title and footer. It is off until you switch it on.

## Switching it on and off

`网站管理 → 播客` is the podcast's admin, and the switch is at the top of it. The
podcast is off by default. `开启播客` brings up the show page `/podcast/`, episodes
at `/podcast/<number>` with comments, the RSS feed `/podcast/feed.xml`, and a
`播客` link in the blog menu. `从导航隐藏` removes only the menu link; the pages stay
reachable. `关闭播客` takes everything down (those addresses answer 404 and the
sitemap leaves them out) while episodes and audio stay, so it can be switched on
again any time. Episodes can still be managed while it is off.

## Admin

Nothing about the show is preset: until you write them, the name is the site
name plus `播客`, the author is the site name, and the description is empty (the
feed then uses the name). The checklist on the admin page lists what is still
unwritten.

The episode page has its own player (play, progress, skip, speed) that matches the
site; without JavaScript the browser's own audio controls are shown instead.

`/admin/podcast` lists episodes, and `节目设置` holds the show's title,
description, author, **contact email** (Apple and 小宇宙 mail it a code to prove
you own the feed), category, cover and store links. The list warns about what the
feed still lacks (email, cover, published episodes).

An episode has a number (its address), title, summary, Markdown show notes, an
MP3 or M4A file, an optional cover, a release time and two switches (published,
comments). Lines of the show notes that start with a time, such as
`- [01:35] topic`, become buttons that jump the player there.

Audio is stored under `<UPLOAD_FOLDER>/audio/` with a random name and served from
`/files/audio/...`. Length and size are read from the file. The name is the feed's
enclosure URL, so it only changes when you deliberately replace the file.

## Settings

| Variable | Use |
| --- | --- |
| `PODCAST_AUDIO_MAX_MB` | Largest audio upload an admin may make (default 300). Other requests keep the 20 MB limit. |
| `SITE_URL` | Public address of the site, used to build the redirect target. |
| `PODCAST_REDIRECT_HOSTS` | Hostnames that used to be the podcast's own site. |

## Moving the old domain

Point the old hostname at the server and give it a site block that proxies to the
same app (certificates are issued automatically):

```caddy
podcast.example.com {
	reverse_proxy 127.0.0.1:8001
}
```

With `SITE_URL=https://blog.example.com` and
`PODCAST_REDIRECT_HOSTS=podcast.example.com`, every request to that host gets a
`301` to the podcast pages on the main site. The old feed addresses
(`/feed/podcast/`, `/feed/`) go to the new feed, and an old episode address goes
to its episode when the episode was added with `--legacy-path`; anything else lands
on `/podcast/`.

Uploading a large episode through Caddy needs no extra setting (Caddy has no body
limit by default; if you set `request_body max_size`, leave room for the audio).
Gunicorn's `timeout` in `gunicorn.conf.py` already covers a slow upload.

## Moving the feed in Apple Podcasts and 小宇宙

Both read the feed URL they were given. They follow a `301`, and episodes are told
apart by their `<guid>`, so keep each old episode's id (`--feed-guid`, see below);
otherwise the apps list every episode twice. After the redirect works, in Podcasts
Connect change the feed URL to the new one, and in 小宇宙 re-submit it if asked.

## Adding episodes from files

Large files are easier to put on the server and import there than to upload in a
browser:

```bash
flask podcast add --number 4 --title "Episode title" \
  --audio EP004.mp3 --published "2022-11-19 23:49" \
  --notes EP-004.md --cover cover.png \
  --legacy-path "/2022/11/19/ep-004-episode-title/" \
  --feed-guid "https://podcast.example.com/?p=98"
```

`--published` is in the display time zone. `--draft` leaves the episode unpublished.

## Backups

The audio is part of `UPLOAD_FOLDER`, so it is covered wherever the uploads are
backed up. It is far bigger than the images, which matters for the deploy backup.

The whole site, audio included, can be copied to Cloudflare R2 with
`scripts/backup_r2.sh`; see the Backup section of the README.
