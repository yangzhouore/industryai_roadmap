import {notFound} from 'next/navigation';
import {getIssues,isLocale} from '@/lib/data';

// This guard sits above this segment's loading boundary. Resolve missing
// resources before streaming can commit successful response headers.
export default async function PublicRouteLayout({children,params}:{children:React.ReactNode;params:Promise<{locale:string;path?:string[]}>}){
  const {locale,path=[]}=await params;
  if(!isLocale(locale))notFound();
  if(path.length===0)return children;
  if(path.length===1&&['archive','search','methodology','privacy','whatsnew'].includes(path[0]))return children;
  if(path[0]!=='digest'||!(path.length===2||(path.length===3&&path[2]==='sources')))notFound();
  const issues=await getIssues();
  if(!issues.some(issue=>issue.slug===path[1]))notFound();
  return children;
}
