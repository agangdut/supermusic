# 🎼 MuScriptor, explained

A study guide to **MuScriptor: An Open Model for Multi-Instrument Music Transcription** by Simon Rouard, Michael Krause, Axel Roebel, Carl-Johann Simon-Gabriel and Alexandre Défossez (Kyutai, Mirelo AI, IRCAM). ISMIR 2026, [arXiv 2607.08168](https://arxiv.org/abs/2607.08168). Written for a college student new to machine learning, and tied to how SuperMusic uses the model.

Most transcription models learn mostly from fake audio, made by playing MIDI files through software instruments, and they fall apart on real records. This paper shows the fix is mostly data: pre-train on lots of fake audio, fine-tune on 11,000 hours of real songs with lined-up notes, then polish with a little reinforcement learning. The result is the model SuperMusic now uses for Full band and Auto.

## The paper in five sentences

- Automatic music transcription (AMT) turns a recording into MIDI: which notes, when, how long, and on which instrument.
- The authors keep the model simple (a standard transformer that writes MIDI one token at a time, like a language model writes words) and put the effort into training data.
- Training has three stages: 1.45 million synthetic MIDI renders, then 170,000 real recordings (about 11,000 hours) with notes aligned to the audio, then reinforcement learning on 300 hand-checked songs.
- On their own 372-song test set, the full model scores 48.2 "multi F1" (notes right *and* on the right instrument) against 21.9 for YourMT3+, the previous best open model.
- Code and weights are released, and you can optionally tell the model which instruments are in the song.

## Words you need

| Term | Meaning |
|---|---|
| **AMT** | Automatic music transcription: audio in, notes out. Multi-instrument AMT also says which instrument played each note. |
| **MIDI** | Notes stored as events ("note 60 starts at 1.20 s on the bass track, stops at 1.55 s"), not sound. |
| **Mel-spectrogram** | A picture of sound: time left to right, pitch bottom to top, brightness = loudness, with the pitch axis squashed the way hearing is. MuScriptor reads 100 columns per second, 512 rows high, from 16 kHz mono audio. |
| **Token** | One "word" of output, such as `time=1.20`, `instrument=bass`, `note_on=60`. A transcription is a long sentence of these (the MT3 format). |
| **Decoder-only transformer** | A model that writes output one token at a time, each time looking at everything so far plus the input. GPT works this way. Here the spectrogram goes in as a "prefix", like a prompt. |
| **Teacher forcing** | Normal training: show the correct tokens so far and ask for the next one. |
| **Synthetic data** | Audio made by playing MIDI through a soundfont (recorded instrument samples). Perfectly labelled and free, but it doesn't sound like a produced record. |
| **Alignment / DTW** | Real songs often have a score or MIDI whose timing doesn't match the recording. Dynamic time warping stretches the note timeline until it lines up. |
| **Precision, recall, F1** | Precision: of the notes written, how many are real. Recall: of the real notes, how many were found. F1 combines both. Reported 0–100 in the paper. |
| **Onset / offset / frame / multi F1** | **Onset**: right pitch, start within 50 ms. **Offset**: the end roughly right too. **Frame**: is the right pitch sounding in each 62.5 ms slice (lenient). **Multi**: offset F1 plus the right instrument (strictest). **Drums**: onset F1 on drum hits. |
| **Conditioning** | Extra input that steers the model. Here, an optional list of the song's instruments. |
| **CFG** | Classifier-free guidance: run the model with and without the instrument list and push the answer further toward the "with" version. α = 1 is off, α = 2 is on. Costs a second forward pass. |
| **Reinforcement learning (RL)** | The model tries whole answers, each gets a score, and it's nudged toward higher-scoring ones. |
| **GRPO** | A simple RL recipe: generate a group of answers to the same input and reward each by how much it beats the group average. |
| **Argmax / beam search** | Argmax takes the single most likely next token. Beam search keeps several partial answers and picks the best finished one. The paper uses argmax. |

## The problem

Solo piano is close to solved (SuperMusic's Piano mode scores 0.97 on MAESTRO). Full songs aren't: many instruments, overlapping pitches, distortion, effects, mastering, and very little real audio with correct note labels. MT3 (2022) and YourMT3+ (2024) leaned on synthetic data plus about 250 hours of real audio, mostly single instruments, and do poorly on real records.

The authors' bet: skip architecture tricks, use a plain transformer, and scale the data, especially real data. The paper is mostly a study of what each kind of data contributes.

```
1 · Pre-train                 2 · Fine-tune                    3 · RL polish
1.45M MIDI files rendered  →  170k real recordings, 11k h,  →  300 hand-checked songs,
with 250+ soundfonts          notes aligned by DTW             reward = F1 scores

Multi F1 after each stage:  15.2  →  41.7  →  48.2      (YourMT3+: 21.9)
```

## The data

- **Synthetic.** About 1.45 million MIDI files (Lakh MIDI and commercial sources, mostly pop and classical). They're rendered on the fly: each excerpt gets random pitch shifts, tempo changes, velocity changes, instrument swaps, one of 250+ soundfonts and a slight detune. So the supply is effectively endless.
- **Real.** An internal set of 170,000 recordings (about 11,000 hours) aligned to their notes, with badly aligned pairs thrown out. Piano is in 51% of tracks, distorted guitar 47%, electric bass 43%, drums 32%, voice 21%. **This dataset isn't released**, so the training can't be reproduced, only the weights used.
- **RL and test sets.** 300 hand-verified tracks for RL and 372 more for testing, with similar titles removed from training. Test songs average about 7 active instruments.

## The model

A decoder-only transformer in four sizes (60M, 100M, 300M, 1.3B parameters). It reads a **5-second** mel-spectrogram plus an optional instrument list (looked up in a learned table and placed before the output), and writes MIDI-like tokens. 128 MIDI instruments are grouped into 36 classes. A song is cut into 5-second segments that are transcribed and joined.

Each input is dropped 20% of the time in training, so the model also works without an instrument list. The list describes the whole song, which keeps labels consistent: without it, a guitar might be called "clean" in one segment and "distorted" in the next.

Training: 1 million steps, batch 64, AdamW, learning rate 1e-4 with warm-up and cosine decay. Inference: argmax decoding with CFG at α = 2.

## Reinforcement learning, step by step

Teacher forcing only shows the model correct prefixes, and its loss (predict the next token) isn't the score we care about (F1). RL scores whole transcriptions instead:

1. Take 8 five-second segments from the 300 checked songs.
2. For each, sample **8** different transcriptions (temperature 0.75).
3. Score each: reward = onset F1 + frame F1 + offset F1.
4. Within each group of 8, subtract the mean and divide by the spread. Better-than-average answers get a positive "advantage".
5. Make high-advantage answers more likely and low-advantage ones less likely.

```
reward r     = F_onset + F_frame + F_offset
advantage Â  = (r − group mean) / (group std + 1e-8)
loss         = − average( Â × log-probability of that transcription )
```

It's a stripped-down GRPO (no clipping, no penalty for drifting from the original model), and it adds 6 to 8 points on every metric from just 300 songs. The model misses fewer notes and places note starts more precisely.

## Results

Table 1 of the paper (1.3B model, CFG off, their test set):

| Model | Onset F1 | Frame F1 | Offset F1 | Drums F1 | Multi F1 |
|---|---|---|---|---|---|
| YourMT3+ | 32.5 | 45.5 | 17.8 | 41.4 | 21.9 |
| Synthetic only | 26.1 | 51.3 | 14.2 | 23.1 | 15.2 |
| + real data | 52.5 | 69.4 | 42.0 | 44.7 | 41.7 |
| **+ RL (MuScriptor)** | **60.4** | **73.3** | **49.0** | **50.2** | **48.2** |

- **Synthetic only isn't enough.** It roughly matches YourMT3+ on frames but is worse on note starts and instruments.
- **Real data is the big jump**, about +20 points on everything. This is the paper's central finding.
- **RL adds the polish** from only 300 songs.
- **CFG stops mattering after RL.** It lifts the synthetic-only model's onset F1 from 26.1 to 34.5, but the final model scores 60.4 either way, so the second forward pass can be skipped.

### Do the two kinds of data help each other?

Figure 4 trains with 0–100% of the real data, with and without synthetic pre-training. With only **1%** of the real data (about 110 hours), pre-training lifts offset F1 from **9.9 to 33.4**. With all of it, the gain shrinks to 41.0 → 42.3. So synthetic pre-training matters most when real data is scarce, which is exactly SuperMusic's situation.

### On other people's test sets

Their test set shares a source with the training data, so Table 2 checks 8 public datasets neither model trained on (multi F1 unless noted):

| Dataset | What it is | YourMT3+ | MuScriptor |
|---|---|---|---|
| RWC-P | Japanese pop | 19.1 | **25.6** |
| RWC-J | Jazz | 26.4 | **31.8** |
| RWC-G | Mixed genres | 17.2 | **23.7** |
| RWC-C | Classical | **40.5** | 36.0 |
| RWC-R | Royalty-free | **23.1** | 20.3 |
| Bach10 | Chamber, 4 instruments | 26.4 | **34.7** |
| Dagstuhl ChoirSet | Choir | 2.6 | **11.5** |
| Dagstuhl ChoirSet, *onset F1* | | **22.3** | 14.4 |

MuScriptor wins most but not all. On voices it knows *which* pitch is sounding (ChoirSet frame F1 80.7 vs 51.0) but places note starts worse.

## What else they tested

- **Model size** (trained on real data only): multi F1 35.2 (60M), 38.2 (100M), 39.7 (300M), 40.5 (1.3B). Going from 300M to 1.3B buys under a point for 4× the size.
- **Instrument list:** supplying the true list lifts multi F1 from 38.7 to 40.5.
- **Input type:** mel-spectrogram beats CQT (slightly), MERT embeddings (36.8 vs 39.7 multi) and EnCodec tokens (28.9). Features close to the raw signal suit transcription. That's the opposite of the [Music Map](../music-map.md#research-would-a-music-model-map-better), where MERT and CLAP beat hand-made features, and it makes sense: the map wants *what a song is like*, transcription wants *exactly which frequency starts when*.
- **Overlapping notes:** the token format can't hold the same instrument playing the same pitch twice at once (a re-struck held note). Keeping such notes in the test drops multi F1 from 48.2 to 42.0, so it happens often.

## Limitations

Some stated by the authors, some our reading.

- The real training data is private.
- The headline test set comes from the same source as the training data; the public sets are small and mostly not modern pop.
- Weights are non-commercial (CC BY-NC 4.0).
- 5-second windows: long notes and instrument labels can break at the joins.
- No overlapping same-pitch notes on one instrument.
- Sung note starts are weak (ChoirSet onset F1 14.4).
- No velocity: it says which notes and when, not how loud.
- No speed numbers, and only argmax decoding tested.

## What it means for SuperMusic

MuScriptor's "medium" model (the 300M class) is the default **Full band** engine, and **Auto** uses it for everything except solo piano. It runs in its own container (`services/muscriptor`) and needs `HF_TOKEN`; see [configuration](../configuration.md#model-servers-muscriptor-yourmt3-game).

### 1. Our benchmark agrees with the paper

On MulTTiPop (169 real pop clips none of the models trained on), from [transcription accuracy](../transcription-accuracy.md#real-pop-songs-multtipop):

| Mode | Overall F1 |
|---|---|
| General (Basic Pitch) | 0.143 |
| Full band (YourMT3+) | 0.352 |
| **Full band (MuScriptor)** | **0.474** |

That's an independent check on modern pop, the music users actually feed in. The gap is smaller than the paper's (48.2 vs 21.9) as expected: our scoring ignores which instrument played pitched notes, and the paper's test set shares a source with its training data. The cost is speed: about 0.8 s per second of music on the RTX 2060, roughly 3× YourMT3+, because it writes every note token by token, 5 seconds at a time.

### 2. Medium is the right size for an RTX 2060

The model-size table shows 300M loses under a point against 1.3B, and the large model doesn't fit in 6 GB anyway. Those models were trained on real data only, so the released checkpoints may differ slightly, but the trend should hold.

### 3. The pending experiments, read through the paper

`scripts/eval_pop.py` can run three variants. These are predictions, not results:

- **`muscriptor_fast`** transcribes 4 sections at once. The model already works on separate 5 s segments, so the notes shouldn't change much; the risk is rougher joins. Expect about 3× faster with a small drop. If the drop is tiny, fast could become the default.
- **`muscriptor_beam`** keeps 3 alternatives while decoding. The paper never tested this. RL already sharpened the model's top choice, which usually means beam search adds little. Expect a small or no gain at about 3× the time.
- **`muscriptor_stems`** runs Demucs first, then MuScriptor per stem with an instrument list limited to that stem. It uses the paper's instrument conditioning (+1.8 multi F1 when the list is right), but the model was trained on full mixes, and our [voice test](../transcription-accuracy.md#voices) found Demucs artefacts made Full band *worse* (piano F1 0.908 → 0.855). Expect better instrument labels and possibly worse notes.

### 4. GAME for the lead vocal fits the paper's weak spot

MuScriptor knows which pitch voices are on but places sung note starts poorly. That's why Full band and Auto hand the lead vocal to **GAME**, a singing-only model, and replace MuScriptor's voice track with it. The comparison (`muscriptor_vocal` vs `muscriptor_game`, "Vocal F1" in `eval_pop.py`) will show whether it pays off.

### 5. Try turning CFG off for speed

The paper's final model scores the same with CFG off, which skips a second pass through the model each step. If the `muscriptor` package lets us set the guidance strength, Full band could get close to twice as fast for free. Not yet checked whether the package exposes it, and the medium model may behave differently, so benchmark before changing the default.

### 6. Fine-tuning on our own data

[Training data](../training-data.md) plans an eventual fine-tune (Pop2Piano covers first). Two findings help: after pre-training, 1% of the real data (about 110 hours) took offset F1 from 9.9 to 33.4, and 300 carefully checked songs were enough for RL to add 6+ points. The catch is compute: fine-tuning a 300M model in 6 GB is tight (it would need something like LoRA adapters or a rented GPU), and the non-commercial licence carries over to a fine-tuned version.

### 7. Smaller things to keep in mind

- **Note loudness comes from SuperMusic**, since the model writes no velocities. The app shapes each note's loudness from the audio afterwards.
- **Re-struck notes can disappear.** A held note struck again at the same pitch on the same instrument loses one of the two, which can make sustained piano parts in Full band sound thin.
- **Piano isn't benchmarked yet.** MuScriptor hasn't been run on MAESTRO or MusicNet here. Piano is its most common training instrument, but the Piano model's 0.97 is a high bar.

## Suggested order

1. Run the pending experiments (`muscriptor_fast`, `muscriptor_beam`, `muscriptor_stems`) and the vocal comparison on MulTTiPop. That settles the defaults and whether GAME stays.
2. Check whether the package exposes CFG strength, and if so benchmark it off.
3. Benchmark MuScriptor on MAESTRO and MusicNet so Auto's piano and classical choices rest on numbers.
4. Fine-tune only once a few hundred clean pairs exist, starting from MuScriptor medium.

---

Paper numbers come from its Tables 1–5 and Figures 1–4. SuperMusic numbers come from [transcription-accuracy.md](../transcription-accuracy.md). Predictions about the pending experiments are inferences, not results. Links: [paper](https://arxiv.org/abs/2607.08168) · [code](https://github.com/muscriptor/muscriptor) · [weights](https://huggingface.co/MuScriptor/muscriptor-medium).
