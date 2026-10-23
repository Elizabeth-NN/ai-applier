import { clerkMiddleware } from "@clerk/nextjs/server";

export default clerkMiddleware(async (auth, request) => {
  if (request.nextUrl.pathname.startsWith("/dashboard")) {
    await auth.protect();
  }
});

export const config = {
  matcher: ["/dashboard(.*)"],
};
