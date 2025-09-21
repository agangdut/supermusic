import Link from 'next/link';
import Image from 'next/image';
import logo from '../public/logo.png';

export default function Navbar() {
  return (
    <nav className="flex items-center justify-between bg-white shadow-md p-4">
      <div className="flex items-center space-x-2">
        <Image src={logo} alt="SuperMusic Logo" width={40} height={40} />
        <span className="text-xl font-semibold">SuperMusic</span>
      </div>
      <div className="space-x-4">
        <Link href="/">Home</Link>
        <Link href="/upload">Upload</Link>
      </div>
    </nav>
  );
}
