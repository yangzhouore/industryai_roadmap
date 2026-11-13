export type Locale = 'en' | 'zh';
export type Text = Record<Locale,string>;
export interface Source {id:string; name:string; url:string; publishedAt:string; eventAt:string|null; timezone:string; synthetic:boolean; excerpt:Text;}
export interface Story {id:string; category:string; maturity:string; company:string; kind:'feature'|'quick_bite'; title:Text; summary:Text; why:Text; limitation:Text; sourceIds:string[]; evidenceStatus:'verified'|'synthetic'; score:number;}
export interface Issue {id:string; slug:string; date:string; state:'draft'|'validated'|'published'; validated:boolean; synthetic:boolean; title:Text; introduction:Text; sources:Source[]; stories:Story[];}
