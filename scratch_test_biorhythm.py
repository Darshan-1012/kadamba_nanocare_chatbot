"""Test: extract images from BioWell PDF, focusing on the biorhythm graph page."""
import pdfplumber
import os
from PIL import Image
import io

pdf_path = r"context\input\BIOWELL.pdf"
out_dir = "scratch_biorhythm_images"
os.makedirs(out_dir, exist_ok=True)

with pdfplumber.open(pdf_path) as pdf:
    print(f"Total pages: {len(pdf.pages)}")
    for i, page in enumerate(pdf.pages):
        text_start = (page.extract_text() or "")[:80].strip().replace("\n", " ")
        imgs = page.images
        print(f"  Page {i+1}: {len(imgs)} images | {text_start}")

        # For pages with images, try to extract them
        if imgs:
            for j, img_info in enumerate(imgs):
                print(f"    img[{j}]: w={img_info.get('width', '?')}, h={img_info.get('height', '?')}, srcsize={img_info.get('srcsize', '?')}")

    # Also try page.to_image() to render the biorhythm page as an image
    # The biorhythm page is typically around page 20
    for test_page_idx in range(min(len(pdf.pages), 35)):
        text = (pdf.pages[test_page_idx].extract_text() or "")
        if "Biorhythm" in text or "biorhythm" in text.lower():
            print(f"\n=== BIORHYTHM PAGE FOUND: Page {test_page_idx + 1} ===")
            print(f"Text content:\n{text[:300]}")

            # Render as image
            page_img = pdf.pages[test_page_idx].to_image(resolution=200)
            out_path = os.path.join(out_dir, f"biorhythm_page_{test_page_idx+1}.png")
            page_img.save(out_path)
            print(f"Saved page render to: {out_path}")
            break
