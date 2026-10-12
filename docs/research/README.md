# 📄 Research papers

Papers that shaped SuperMusic, with what each one means for this project. The PDFs aren't kept in the repo (we don't have the right to redistribute them); follow the links to read them. Each paper also has a study guide written for a college student new to the field (the guides are private claude.ai pages, so only the project owner can open them unless shared).

| Paper | Area |
|---|---|
| [MuScriptor: An Open Model for Multi-Instrument Music Transcription](#muscriptor) | MIDI transcription |
| [Diffusable Latents from Structure-Agnostic Distillation](#diffusable-latents-from-structure-agnostic-distillation) | Music Map embeddings |

## MuScriptor

**MuScriptor: An Open Model for Multi-Instrument Music Transcription** (ISMIR 2026)
Simon Rouard, Michael Krause, Axel Roebel, Carl-Johann Simon-Gabriel, Alexandre Défossez (Kyutai, Mirelo AI, IRCAM)
[arXiv:2607.08168](https://arxiv.org/abs/2607.08168) · [code](https://github.com/muscriptor/muscriptor) · [weights](https://huggingface.co/MuScriptor/muscriptor-medium) · [study guide](https://claude.ai/artifact/HnjW95Bn9hS5RWe7Pnojh5)

**Summary.** A plain decoder-only transformer that turns a full mix into multi-instrument MIDI. It is pre-trained on 1.45M synthetic MIDI renders, then fine-tuned on 170k real recordings (about 11,000 hours) with aligned notes, then polished with reinforcement learning on 300 high-quality transcriptions. Synthetic data alone isn't enough for real songs; adding real recordings is what makes it work. You can also tell it which instruments are present.

**For SuperMusic.** It's the default Full band engine since it won our MulTTiPop pop benchmark (0.47 overall F1 against 0.35 for YourMT3+). See [transcription accuracy](../transcription-accuracy.md#real-pop-songs-multtipop), [training data](../training-data.md) and [configuration](../configuration.md#model-servers-muscriptor-yourmt3-game). Weights are non-commercial only (CC BY-NC 4.0).

## Diffusable Latents from Structure-Agnostic Distillation

**Diffusable Latents from Structure-Agnostic Distillation** (2026)
Adrien Ramanana Rahary, Nicolas Dufour, Patrick Pérez, David Picard (ENPC, Kyutai)
[arXiv:2609.39657](https://arxiv.org/abs/2609.39657) · [code](https://github.com/AdrienRR/structure-agnostic-distillation) · [blog post](https://kyutai.org/blog/2026-09-28-structure-agnostic-distillation) · [study guide](https://claude.ai/artifact/Gq7MtdmNULnwmTh6mmekyH)

**Summary.** Image generators learn faster when their compressed "latent" space is taught to resemble a big pretrained model's features. The paper shows you don't need to match those features position by position: matching one pooled (averaged) vector per image works as well or slightly better, even across modalities, and so does matching only each image's nearest neighbours.

**For SuperMusic.** It's an image paper, but two ideas carry over to the Music Map: one time-averaged vector per song is enough to capture what a model "knows" about it, and nearest-neighbour overlap is a good way to compare two embedding spaces. Both are used in the [CLAP and MERT experiment](../music-map.md#research-would-a-music-model-map-better). It doesn't help MIDI accuracy.
