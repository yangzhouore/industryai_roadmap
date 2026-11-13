import {getRequestConfig} from 'next-intl/server';
export default getRequestConfig(async({requestLocale})=>{const requested=await requestLocale;return{locale:requested==='zh'?'zh':'en',timeZone:'UTC',messages:{}};});
