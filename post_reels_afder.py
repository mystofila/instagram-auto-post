name: AFDER — Carrousel & Reels Instagram

on:
  schedule:
    # Carrousel tous les jours à 9h42 (UTC)
    - cron: '42 9 * * *'
    # Reels : lundi=1, mercredi=3, vendredi=5 à 12h00 (UTC)
    - cron: '0 12 * * 1,3,5'
  workflow_dispatch:
    inputs:
      force_type:
        description: 'Forcer un type (carousel / reel / les deux)'
        required: false
        default: 'auto'

jobs:
  post:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install system dependencies
        run: |
          sudo apt-get update -qq
          sudo apt-get install -y \
            fonts-noto-color-emoji \
            fonts-open-sans \
            libcairo2-dev \
            libffi-dev \
            pkg-config \
            ffmpeg

      - name: Install Python dependencies
        run: |
          pip install \
            groq \
            requests \
            Pillow \
            cloudinary \
            cryptography \
            pynacl \
            cairosvg \
            google-genai \
            moviepy \
            numpy

      # ── Déterminer ce qu'on publie ────────────────────────────────────────
      - name: Déterminer le type de publication
        id: type
        run: |
          FORCE="${{ github.event.inputs.force_type }}"
          DAY=$(date +%u)   # 1=lundi … 7=dimanche
          CRON_MIN=$(date +%M)
          CRON_H=$(date +%H)

          if [ "$FORCE" = "carousel" ]; then
            echo "run_carousel=true"  >> $GITHUB_OUTPUT
            echo "run_reel=false"     >> $GITHUB_OUTPUT
          elif [ "$FORCE" = "reel" ]; then
            echo "run_carousel=false" >> $GITHUB_OUTPUT
            echo "run_reel=true"      >> $GITHUB_OUTPUT
          elif [ "$FORCE" = "les deux" ]; then
            echo "run_carousel=true"  >> $GITHUB_OUTPUT
            echo "run_reel=true"      >> $GITHUB_OUTPUT
          else
            # Auto : carrousel à 09h42, reels à 12h00 lun/mer/ven
            if [ "$CRON_H" = "09" ] || [ "$CRON_H" = "10" ]; then
              echo "run_carousel=true" >> $GITHUB_OUTPUT
            else
              echo "run_carousel=false" >> $GITHUB_OUTPUT
            fi
            if ( [ "$DAY" = "1" ] || [ "$DAY" = "3" ] || [ "$DAY" = "5" ] ) && \
               ( [ "$CRON_H" = "12" ] || [ "$CRON_H" = "13" ] ); then
              echo "run_reel=true" >> $GITHUB_OUTPUT
            else
              echo "run_reel=false" >> $GITHUB_OUTPUT
            fi
          fi

      # ── Carrousel ─────────────────────────────────────────────────────────
      - name: Publier le carrousel
        if: steps.type.outputs.run_carousel == 'true'
        env:
          GROQ_API_KEY:              ${{ secrets.GROQ_API_KEY }}
          INSTAGRAM_ACCESS_TOKEN:    ${{ secrets.INSTAGRAM_ACCESS_TOKEN }}
          INSTAGRAM_USER_ID:         ${{ secrets.INSTAGRAM_USER_ID }}
          CLOUDINARY_CLOUD_NAME:     ${{ secrets.CLOUDINARY_CLOUD_NAME }}
          CLOUDINARY_API_KEY:        ${{ secrets.CLOUDINARY_API_KEY }}
          CLOUDINARY_API_SECRET:     ${{ secrets.CLOUDINARY_API_SECRET }}
          GH_TOKEN:                  ${{ secrets.GH_TOKEN }}
        run: python post.py

      # ── Reels ─────────────────────────────────────────────────────────────
      - name: Publier le Reel
        if: steps.type.outputs.run_reel == 'true'
        env:
          GEMINI_API_KEY:            ${{ secrets.GEMINI_API_KEY }}
          INSTAGRAM_ACCESS_TOKEN:    ${{ secrets.INSTAGRAM_ACCESS_TOKEN }}
          INSTAGRAM_USER_ID:         ${{ secrets.INSTAGRAM_USER_ID }}
          CLOUDINARY_CLOUD_NAME:     ${{ secrets.CLOUDINARY_CLOUD_NAME }}
          CLOUDINARY_API_KEY:        ${{ secrets.CLOUDINARY_API_KEY }}
          CLOUDINARY_API_SECRET:     ${{ secrets.CLOUDINARY_API_SECRET }}
          GH_TOKEN:                  ${{ secrets.GH_TOKEN }}
        run: python post_reels_afder.py
