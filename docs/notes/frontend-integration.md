# Frontend Integration Summary

This document describes the frontend changes made to integrate with the backend API endpoints for transcriptions and other operations.

## Changes Made

### 1. Created API Fetcher Utility (`frontend/utils/fetcher.js`)
- New utility for making API calls to the backend
- Handles JSON and FormData requests
- Uses `NEXT_PUBLIC_API_BASE` environment variable (defaults to `http://localhost:8000`)
- Proper error handling with detailed error messages

### 2. Updated Upload Jobs Hook (`frontend/hooks/useUploadJobs.js`)
- **File Upload Flow**: Now properly uploads files first, then creates jobs
- **Two-Step Process**:
  1. Upload file to `/upload/audio` or `/upload/csv` → get server path
  2. Create job with server path (e.g., `/midi/convert`, `/stems/separate`, `/csv/enrich`)
- **Job Polling**: Automatically polls job status every 2 seconds
- **Status Mapping**: Maps backend statuses ("done", "error") to frontend statuses ("success", "failed")
- **Artifact Extraction**: Automatically extracts artifacts when jobs complete
- **Real-time Updates**: Jobs update in real-time as they progress

### 3. Updated API Library (`frontend/lib/api.js`)
- Uses the new fetcher utility
- Properly handles job polling with terminal status detection
- Artifact URL normalization for serving from `/artifacts` endpoint

### 4. Updated Job Components
- **JobCard**: Now handles both "error" and "failed" statuses, displays `error_detail`
- **ResultsCard**: Shows both job list and latest artifacts
- **Status Badge**: Supports both frontend and backend status values

### 5. Status Mapping
The frontend now properly maps backend statuses:
- `queued` → `queued`
- `running` → `running`
- `done` → `success`
- `error` → `failed`
- `cancelled` → `canceled`

## API Flow

### MIDI Transcription Flow
1. User selects audio file
2. User clicks "Transcribe → MIDI"
3. Frontend uploads file to `/upload/audio`
4. Backend returns `{ success: true, path: "/path/to/file.mp3" }`
5. Frontend calls `/midi/convert` with `{ source_path: "/path/to/file.mp3" }`
6. Backend returns job object with `id`, `status`, `job_type`
7. Frontend polls `/midi/jobs/{id}` every 2 seconds
8. When job completes, artifacts are extracted and displayed

### Stem Separation Flow
1. User selects audio file
2. User clicks "Separate Stems"
3. Frontend uploads file to `/upload/audio`
4. Frontend calls `/stems/separate` with `{ audio_path: "/path/to/file.mp3" }`
5. Frontend polls `/stems/jobs/{id}` until complete
6. Artifacts (vocals.wav, drums.wav, etc.) are displayed

### CSV Enrichment Flow
1. User selects CSV file
2. User clicks "Enrich CSV"
3. Frontend uploads file to `/upload/csv`
4. Frontend calls `/csv/enrich` with `{ csv_path: "/path/to/file.csv" }`
5. Frontend polls `/csv/jobs/{id}` until complete
6. Enriched CSV artifact is displayed

## Environment Variables

Create a `.env.local` file in the frontend directory:

```env
NEXT_PUBLIC_API_BASE=http://localhost:8000
NEXT_PUBLIC_ARTIFACT_BASE=http://localhost:8000/artifacts
```

## Testing the Integration

1. **Start the backend**:
   ```bash
   cd backend
   uvicorn app.main:app --reload
   ```

2. **Start the frontend**:
   ```bash
   cd frontend
   npm run dev
   ```

3. **Test MIDI Transcription**:
   - Go to `/upload` page
   - Select an audio file (MP3, WAV, etc.)
   - Click "Transcribe → MIDI"
   - Watch the job progress in real-time
   - When complete, download the MIDI file from artifacts

4. **Test Stem Separation**:
   - Select an audio file
   - Click "Separate Stems"
   - Wait for completion
   - Download individual stem files (vocals, drums, bass, other)

5. **Test CSV Enrichment**:
   - Select a CSV file with track metadata
   - Click "Enrich CSV"
   - Wait for completion
   - Download the enriched CSV

## Key Features

✅ **Real-time Job Updates**: Jobs update automatically as they progress
✅ **Progress Tracking**: Progress bars show job completion percentage
✅ **Artifact Management**: Completed artifacts are automatically extracted and displayed
✅ **Error Handling**: Proper error messages displayed to users
✅ **File Upload**: Secure file upload with validation
✅ **Status Mapping**: Seamless mapping between backend and frontend statuses

## Troubleshooting

### Jobs not updating
- Check that `NEXT_PUBLIC_API_BASE` is set correctly
- Verify backend is running on the correct port
- Check browser console for API errors

### Artifacts not displaying
- Verify `NEXT_PUBLIC_ARTIFACT_BASE` is set correctly
- Check that backend `/artifacts` endpoint is mounted
- Verify artifact paths in job results

### Upload fails
- Check file size limits
- Verify file format is supported (MP3, WAV, FLAC for audio; CSV for data)
- Check backend upload directory permissions

