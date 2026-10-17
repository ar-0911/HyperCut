import type {Metadata} from 'next';
import type {ReactNode} from 'react';
import './globals.css';

export const metadata: Metadata = {title: 'HyperCut', description: 'Turn talking-head footage into a short'};

export default function RootLayout({children}: {children: ReactNode}) {
	return (
		<html lang="en">
			<body>
				<header className="top">
					<a href="/">HyperCut</a>
				</header>
				<main>{children}</main>
			</body>
		</html>
	);
}
