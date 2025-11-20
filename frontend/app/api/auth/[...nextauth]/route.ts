import NextAuth, { AuthOptions } from "next-auth";
import GoogleProvider from "next-auth/providers/google";
import EmailProvider from "next-auth/providers/email";
import { PrismaAdapter } from "@auth/prisma-adapter";
import { prisma } from "../../../../lib/prisma";

/**
 * Auth.js configuration:
 * - Stores users/sessions via Prisma.
 * - Enables Google OAuth and Email magic-link.
 */
const authOptions: AuthOptions = {
  adapter: PrismaAdapter(prisma),
  session: {
    strategy: "jwt", // keep JWT sessions so Express can verify tokens
  },
  providers: [
    GoogleProvider({
      clientId: process.env.GOOGLE_CLIENT_ID ?? "",
      clientSecret: process.env.GOOGLE_CLIENT_SECRET ?? "",
    }),
    EmailProvider({
      server: {
        host: process.env.EMAIL_SERVER_HOST,
        port: Number(process.env.EMAIL_SERVER_PORT),
        auth: {
          user: process.env.EMAIL_SERVER_USER,
          pass: process.env.EMAIL_SERVER_PASSWORD,
        },
      },
      from: process.env.EMAIL_FROM,
    }),
  ],
  callbacks: {
    /**
     * Add the user ID to the JWT so backend services
     * can identify the caller.
     */
    async jwt({ token, user }) {
      if (user) {
        token.id = user.id;
      }
      return token;
    },
    /**
     * Expose the user ID on the session object for the client.
     */
    async session({ session, token }) {
      if (session.user && token.id) {
        session.user.id = token.id as string;
      }
      return session;
    },
  },
  pages: {
    signIn: "/auth/signin", // optional custom sign-in page (can build later)
  },
  secret: process.env.AUTH_SECRET,
};

const handler = NextAuth(authOptions);

// App Router requires both GET and POST exports, re-export handler directly
export { handler as GET, handler as POST };