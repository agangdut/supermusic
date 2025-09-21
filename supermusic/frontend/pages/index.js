import Head from 'next/head';
import Navbar from '../components/Navbar';
import Player from '../components/Player';

export default function Home() {
  return (
    <>
      <Head>
        <title>SuperMusic</title>
        <meta name="description" content="SuperMusic – Explore and Transcribe Music" />
      </Head>
      <Navbar />
      <main className="flex flex-col items-center justify-center min-h-screen bg-gray-50">
        <h1 className="text-4xl font-bold mt-8">Welcome to SuperMusic</h1>
        <p className="mt-4 text-lg text-gray-600">Upload and explore your tracks</p>
        <div className="mt-8">
          <Player />
        </div>
      </main>
    </>
  );
}
