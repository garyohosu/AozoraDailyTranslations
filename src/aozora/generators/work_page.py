"""Agent 6A — WorkPageGenerator: generate individual work HTML pages."""

from __future__ import annotations

import html
import os
import re

from aozora.models import TranslationResult, WorkEntry

# SPEC.md §3.2: スラッグ最大 50 文字
_SLUG_MAX_LEN = 50


class WorkPageGenerator:
    def generate(self, metadata: WorkEntry, translation: TranslationResult, date: str) -> str:
        """作品ページ HTML を生成して返す。"""
        slug = self._generate_slug(metadata.title_en, date)
        dir_slug = self._check_slug_collision(slug.replace(f"{date}-", ""), date)
        return self._apply_template(
            {
                "date": date,
                "slug": dir_slug,
                "title_en": metadata.title_en,
                "author_en": metadata.author_en,
                "genre": metadata.genre,
                "card_url": metadata.aozora_card_url,
                "translation_en": translation.translation_en,
                "introduction_en": translation.introduction_en,
                "source_engine": translation.source,
            }
        )

    # ------------------------------------------------------------------
    # スラッグ生成 (SPEC.md §3.2)
    # ------------------------------------------------------------------

    def _generate_slug(self, title_en: str, date: str) -> str:
        """title_en → kebab-case slug（最大 50 文字、単語境界で切り詰め）。"""
        # 小文字化
        slug = title_en.lower()
        # アポストロフィ等はハイフンを挟まず除去
        slug = re.sub(r"[''`]", "", slug)
        # 空白・特殊文字をハイフンへ
        slug = re.sub(r"[^a-z0-9]+", "-", slug)
        # 先頭・末尾のハイフンを除去
        slug = slug.strip("-")
        # 連続ハイフンを単一化
        slug = re.sub(r"-{2,}", "-", slug)
        # 最大長で単語境界切り詰め
        if len(slug) > _SLUG_MAX_LEN:
            slug = slug[:_SLUG_MAX_LEN].rstrip("-")
            # ハイフン直前で切り詰め（単語境界）
            last_hyphen = slug.rfind("-")
            if last_hyphen > 0:
                slug = slug[:last_hyphen]
        return slug

    # ------------------------------------------------------------------
    # スラッグ衝突チェック (SPEC.md §3.2)
    # ------------------------------------------------------------------

    def _check_slug_collision(self, slug: str, date: str, base_dir: str = ".") -> str:
        """同日 slug が衝突する場合は -2, -3 ... と連番を付与して返す。
        衝突がなければ {date}-{slug} をそのまま返す。
        """
        candidate = f"{date}-{slug}"
        works_dir = os.path.join(base_dir, "works")
        if not os.path.exists(os.path.join(works_dir, candidate)):
            return candidate
        suffix = 2
        while os.path.exists(os.path.join(works_dir, f"{candidate}-{suffix}")):
            suffix += 1
        return f"{candidate}-{suffix}"

    # ------------------------------------------------------------------
    # XSS エスケープ (SPEC.md §12.3)
    # ------------------------------------------------------------------

    def _xss_escape(self, text: str) -> str:
        """HTML 特殊文字をエスケープして XSS を防ぐ。"""
        return html.escape(text, quote=True)

    # ------------------------------------------------------------------
    # テンプレート適用
    # ------------------------------------------------------------------

    def _apply_template(self, data: dict) -> str:
        """安全にエスケープした値を HTML テンプレートに埋め込んで返す。
        SPEC.md §13.1 (AdSense), §13.2 (CSP), §13.3 (英語のみ),
        §4.4 (必須クレジット) に準拠。
        title_ja / author_ja はこのテンプレートで一切参照しない。
        """
        title = self._xss_escape(data["title_en"])
        author = self._xss_escape(data["author_en"])
        card_url = self._xss_escape(data["card_url"])
        body = self._xss_escape(data["translation_en"])
        intro = self._xss_escape(data["introduction_en"])
        date = self._xss_escape(data["date"])

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title} — {author} | Aozora Daily Translations</title>
  <!-- Content Security Policy (SPEC.md §13.2) -->
  <meta http-equiv="Content-Security-Policy"
        content="default-src 'self';
                 script-src 'self' https://pagead2.googlesyndication.com https://cdn.jsdelivr.net 'unsafe-inline';
                 style-src 'self' https://cdn.jsdelivr.net https://fonts.googleapis.com 'unsafe-inline';
                 font-src 'self' https://fonts.gstatic.com https://cdn.jsdelivr.net;
                 img-src 'self' https:;
                 frame-src https://googleads.g.doubleclick.net;">
  <!-- Google AdSense (SPEC.md §13.1) -->
  <script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-6743751614716161"
          crossorigin="anonymous"></script>
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Libre+Baskerville:wght@700&family=Inter:wght@400;500;700&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="../../assets/style.css">
</head>
<body class="bg-body-tertiary">
  <header class="py-3 border-bottom bg-white">
    <div class="container d-flex justify-content-between align-items-center">
      <a href="../../index.html" class="text-decoration-none fw-bold site-brand">Aozora Daily Translations</a>
      <a href="../../index.html" class="btn btn-sm btn-outline-secondary">All works</a>
    </div>
  </header>

  <main class="container my-4">
    <article class="card border-0 shadow-sm">
      <div class="card-body p-4 p-md-5">
      <h1 class="mb-1 display-6">{title}</h1>
      <p class="text-muted mb-3">by {author} &mdash; {date}</p>

      <!-- Introduction (SPEC.md §5.2) -->
      <section class="mb-4" aria-label="Introduction">
        <p class="lead">{intro}</p>
      </section>

      <!-- Translation body -->
      <section class="mb-5" aria-label="Translation">
        <p>{body}</p>
      </section>

      <!-- Mandatory credits (SPEC.md §4.4) -->
      <footer class="border-top pt-3 mt-4 text-muted small">
        <p>Source (Japanese text): <strong>Aozora Bunko (Public Domain in Japan)</strong></p>
        <p>Work: <em>{title}</em> / Author: <em>{author}</em></p>
        <p>Aozora Bunko card: <a href="{card_url}" target="_blank" rel="noopener">{card_url}</a></p>
        <p>Input &amp; Proofreading: See Aozora Bunko card for volunteer contributors</p>
        <p>English translation license: <strong>CC0 1.0 Universal</strong></p>
        <p class="fst-italic">
          This translation is automatically generated and may contain errors.
          Please refer to the original Japanese text for authoritative meaning.
        </p>
      </footer>
      </div>
    </article>
  </main>
</body>
</html>"""
