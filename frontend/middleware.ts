import { NextResponse } from 'next/server'
import type { NextRequest } from 'next/server'

// Basic middleware to protect routes
export function middleware(request: NextRequest) {
    const userId = request.cookies.get('sentimind_user_id')?.value

    // Protected routes require a user_id cookie
    const protectedRoutes = ['/dashboard', '/profile']
    const isProtectedRoute = protectedRoutes.some((route) =>
        request.nextUrl.pathname.startsWith(route)
    )

    if (isProtectedRoute && !userId) {
        return NextResponse.redirect(new URL('/login', request.url))
    }

    return NextResponse.next()
}

export const config = {
    matcher: ['/dashboard/:path*', '/profile/:path*'],
}
