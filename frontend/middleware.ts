import { NextResponse } from 'next/server'
import type { NextRequest } from 'next/server'
import { getToken } from 'next-auth/jwt'

const PROTECTED_PREFIXES = ['/dashboard', '/profile', '/chat', '/onboarding']

function applySecurityHeaders(response: NextResponse) {
    response.headers.set('X-Content-Type-Options', 'nosniff')
    response.headers.set('X-Frame-Options', 'DENY')
    response.headers.set('Referrer-Policy', 'no-referrer')
    response.headers.set('Permissions-Policy', 'camera=(), microphone=(self), geolocation=(self)')
    response.headers.set('X-Robots-Tag', 'noindex, nofollow')
    return response
}

export async function middleware(request: NextRequest) {
    const isProtectedRoute = PROTECTED_PREFIXES.some((route) =>
        request.nextUrl.pathname.startsWith(route)
    )

    if (isProtectedRoute) {
        const token = await getToken({
            req: request,
            secret: process.env.NEXTAUTH_SECRET,
        })

        if (!token) {
            return applySecurityHeaders(
                NextResponse.redirect(new URL('/login', request.url))
            )
        }
    }

    return applySecurityHeaders(NextResponse.next())
}

export const config = {
    matcher: ['/dashboard/:path*', '/profile/:path*', '/chat/:path*', '/onboarding/:path*'],
}
