# thyra
Thyra /ˈθaɪ.rə/ is a gateway from photo/video to 3D to dynamic video.

Cross platform PySide 6/Qt based solution.

## Features under development:

- Counting objects (quantitative vision → birds in sky, cars, etc.)

- 3D reconstruction (geometry, physics, realism)

- Video continuation (time, motion, prediction, simulation)

Base use cases: 
- counting very little objects on the image, based on population density.
- ocean waves reconstruction, based on extracting initial conditions and boundary values from image and numerically solving wave differential equation. Parametrize by time 3d numerical solution for ocean wave video continuation. Modelling difraction given obstacles (rocks) on the wave path.

Output masks from labeling tools
 **Semantic / Panoptic segmentation masks**
   * Export **PNG (8-bit)**: each pixel has a class ID (0 = background, 1 = car, 2 = road, …).
   * Export **JSON/COCO**: metadata mapping color/ID → class name.
   *  Optional: **EXR (16-bit float)** soft masks / alpha channels (less common for photogrammetry).

**Instance segmentation masks**

* Export **binary mask per object** (PNG, 0 = background, 255 = object).
* Or **panoptic PNG** where each instance/class combination gets a unique ID/color.
* Metadata in **COCO Panoptic JSON**.

Practical export/import recipes

* **If you want to exclude backgrounds** (sky, ground, moving people):

  * Export semantic masks → convert to binary PNG (0/255) for background vs foreground.
  * Import into Metashape/RealityCapture as exclusion masks.

* **If you want to reconstruct only specific classes** (e.g., cars, trees):

  * Export instance masks → keep only those class IDs → generate PNG masks → import.

* **If you want to weight features** (advanced):

  * Use EXR/float masks in RealityCapture for soft weighting (less common in practice).

# Image segmentation types

Segmentation = labeling pixels, not just detecting bounding boxes.

* **Semantic segmentation**

  * Every pixel is assigned a *class label* (e.g., “car,” “road,” “tree”).
  * Good for tasks where *exact object boundaries* matter but you don’t need to distinguish between instances.
  * **Use cases:** autonomous driving (road vs. sidewalk vs. lane), satellite imagery (land vs. water vs. building), medical imaging (organ boundaries).
  * **Models:** U-Net, DeepLabV3+, SegFormer.

* **Instance segmentation**

  * Similar to semantic segmentation, but different *instances* of the same class are separated (e.g., Car #1 vs Car #2).
  * **Use cases:** retail shelf analysis (counting bottles), crowd counting, biology (counting cells), autonomous driving (distinguishing cars).
  * **Models:** Mask R-CNN, YOLACT, SOLO.

* **Panoptic segmentation**

  * Combination of both: every pixel has a class + instance label.
  * **Use cases:** advanced autonomous driving, complex scene understanding for robotics.
  * **Models:** Panoptic FPN, Panoptic-DeepLab.

---

# Counting objects in images and videos

Counting can be seen as a *derived task* from detection or segmentation.

* **Counting from object detection**

  * Detect objects (YOLO, Faster R-CNN, DETR) → count detections.
  * **Use cases:** vehicle traffic analysis, people counting in security cameras, animal monitoring.
  * **Strengths:** works well when objects are *well separated*.
  * **Weaknesses:** struggles in dense crowds (overlapping objects).

* **Counting from instance segmentation**

  * Segment objects (Mask R-CNN, SOLO) → count instances.
  * **Use cases:** medical imaging (counting cells, tumors), manufacturing QA (counting defects).
  * **Strengths:** robust when objects overlap, as long as segmentation is good.
  * **Weaknesses:** higher computational cost than detection.

* **Density map regression (crowd counting)**

  * Instead of detecting each object, the network predicts a *density heatmap*; integrating it gives total count.
  * **Use cases:** extremely dense crowds, microscopic images with thousands of cells.
  * **Models:** CSRNet, MCNN.
  * **Strengths:** handles severe occlusion, high-density scenes.
  * **Weaknesses:** no precise localization, only counts.

* **Video-specific methods**

  * Tracking-based: detect → track → count (SORT, DeepSORT trackers).
  * Temporal models: combine detection/segmentation with LSTMs or transformers for temporal consistency.
  * **Use cases:** counting people entering/leaving stores, traffic flow monitoring.

---

# VLM comparison table

| Model / Family | Cloud inference availability | Video-suitable | Panoptic-segmentation role (practical) | Pricing style (high level) |
|---|---:|:---:|---|---|
| **OpenAI — GPT-4.1 / GPT-4o (vision-enabled)** | OpenAI API (vision-capable endpoints). | **Partial** — supports image inputs and frame-by-frame multimodal prompts; not a dedicated video API.  [oai_citation:0‡OpenAI](https://openai.com/api/pricing/?utm_source=chatgpt.com) | **Labeling / reasoning / interactive QA & prompting.** Use to name classes, filter/verify panoptic outputs, generate annotation instructions or summaries; not for pixel masks (pair with SAM/Mask R-CNN). | **Token-based** + sometimes per-image accounting; billed per input/output tokens (and image tokenization rules). Good for interactive workflows; expensive if you naively send many full frames.  [oai_citation:1‡OpenAI](https://openai.com/api/pricing/?utm_source=chatgpt.com) |
| **Anthropic — Claude 3 family (Opus / Sonnet / Haiku)** | Anthropic API; also available via **AWS Bedrock**. | **Partial → Yes** for frames & images; Anthropic documents vision support and image understanding. Good for frame-level reasoning; can accept images.  [oai_citation:2‡Anthropic](https://docs.anthropic.com/en/docs/build-with-claude/vision?utm_source=chatgpt.com) | **Labeling / multi-frame reasoning / QA** — excellent at diagram/chart & scene reasoning, good at providing class labels and human-like annotation instructions. Use for class disambiguation and temporal consistency suggestions. | **Token-based** on Anthropic API; via Bedrock model pricing (token I/O on Bedrock, with on-demand / batch / provisioned options). See Bedrock docs for model-specific prices.  [oai_citation:3‡AWS Documentation](https://docs.aws.amazon.com/bedrock/latest/userguide/model-parameters-claude.html?utm_source=chatgpt.com) |
| **Google — Gemini (1.5 / 2.5 family)** | Google **Vertex AI / Gemini API**. | **Yes** — Gemini supports video uploads and dedicated video-understanding endpoints (Vertex/Gemini video docs). Suitable for frame / clip level reasoning.  [oai_citation:4‡Google Cloud](https://cloud.google.com/vertex-ai/generative-ai/docs/multimodal/video-understanding?utm_source=chatgpt.com) | **Labeling / temporal QA / summarization / shot-level instructions.** Use for video-level scene descriptions, temporal instance linking hints, and interactive corrections to panoptic outputs. | **Token / request-based** for Gemini; video features often priced per request or per-second/token depending on operation. Vertex lists input/output pricing tiers.  [oai_citation:5‡Google AI for Developers](https://ai.google.dev/gemini-api/docs/pricing?utm_source=chatgpt.com) |
| **Hugging Face-hosted VLMs (LLaVA, LLava-Gemma, Video-LLaMA, InternVideo, Video-LLaVA, etc.)** | Hugging Face Inference + self-hosting (HF Inference API / deploy to your infra / Hugging Face + AWS/Vertex). | **Partial → Many are explicitly video-capable** (Video-LLaMA / InternVideo) — check model card for each. HF hosts many video-VLMs and allows deploying on cloud infra.  [oai_citation:6‡Hugging Face](https://huggingface.co/models?pipeline_tag=video-text-to-text&utm_source=chatgpt.com) | **Flexible (labeling / frame-level reasoning / prototyping).** Good if you want to self-host or fine-tune: can return class names, temporal annotations, and interact with masks. Combine with local segmentation for masks. | **Hugging Face Inference API: per-request / compute-tier billing; self-hosting: pay cloud infra (instance-hour, GPU).** Model compute cost depends on size.  [oai_citation:7‡Hugging Face](https://huggingface.co/models?pipeline_tag=video-text-to-text&utm_source=chatgpt.com) |
| **Open-source & research VLM building blocks (SAM, BLIP-2, Mask2Former, Mask R-CNN)** | Not hosted as single VLM but available on HF & self-hosted. | **No (not an LLM)** — image/video encoder & mask models; SAM is per-frame mask generator (works on video frames).  [oai_citation:8‡Hugging Face](https://huggingface.co/docs/transformers/en/model_doc/blip?utm_source=chatgpt.com) | **Mask generation / proposal**: produces the pixel masks you need. Pair SAM or Mask2Former with a VLM for labeling/temporal linking. | **Open-source:** no direct licensing cost; compute cost = your infra (GPU instance hours). |
| **Specialized video LLMs (InternVideo, Video-LLaMA2, Video-ChatGPT variants)** | Available on Hugging Face / selective cloud deployments; some vendors provide hosted endpoints. | **Yes** — explicitly designed for temporal / long context video reasoning.  [oai_citation:9‡GitHub](https://github.com/DAMO-NLP-SG/VideoLLaMA2?utm_source=chatgpt.com) | **Temporal instance linking, video Q&A, and long-context scene reasoning.** Use to produce instance IDs, narration, or dataset-level metadata. | **Typically self-host or HF inference pricing; large models cost more (GPU-hour / per-inference).** |

## VLM models usage in a panoptic pipeline (typical pattern):
	1.	Run a mask model (SAM / Mask2Former / Mask R-CNN) on each sampled frame to produce pixel masks.
	2.	Use a VLM (OpenAI / Claude / Gemini / LLaVA family) to label masks, provide open-vocabulary names, resolve ambiguous classes, and produce temporal linking hints (same instance over frames).
	3.	Use the VLM to generate human-readable QA, quality checks, and annotation instructions that humans or downstream heuristics can apply.
	
  
  Video cost control tip: don’t send every raw high-res frame to a cloud LLM. Instead: 
  
  (a) sample frames, 
  
  (b) compress to a few crops or embeddings,
  
  (c) send only masks + a handful of exemplar frames / features to the VLM. This saves token/bandwidth costs (OpenAI / Gemini / Bedrock bill on tokens/images).  ￼
	
  Which cloud to pick for production?

	- best interactive multimodal reasoning with easy integration: OpenAI is great for prototyping (image+text), but costs scale with frames.  ￼
	- enterprise multimodal with region control / provider diversity: AWS Bedrock (Anthropic, Mistral, etc.) — good for model choice & batch modes.
	- first-class video support (native video endpoints): Google Gemini / Vertex AI provides explicit video-understanding APIs and is convenient for video-first tasks.




