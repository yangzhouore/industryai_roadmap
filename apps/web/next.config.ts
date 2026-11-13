import type {NextConfig} from 'next';
import createNextIntlPlugin from 'next-intl/plugin';
// Resolve publication metadata before headers so missing editions return HTTP 404.
// Page loading boundaries remain available for navigation and content rendering.
const config: NextConfig = {transpilePackages:['@industrial/shared'], poweredByHeader:false,htmlLimitedBots:/.*/,async redirects(){return [{source:'/',destination:'/en',permanent:false}];}};
const withNextIntl=createNextIntlPlugin('./src/i18n/request.ts');
export default withNextIntl(config);
