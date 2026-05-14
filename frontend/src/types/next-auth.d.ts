import 'next-auth'
import 'next-auth/jwt'

declare module 'next-auth' {
    interface Session {
        user: {
            /** The backend database user ID (cuid) */
            id: string
            name?: string | null
            email?: string | null
            image?: string | null
        }
    }

    interface User {
        id: string
        name?: string | null
        email?: string | null
    }
}

declare module 'next-auth/jwt' {
    interface JWT {
        id: string
        name?: string | null
        email?: string | null
    }
}
